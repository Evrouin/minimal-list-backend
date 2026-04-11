# Soft Account Deletion with 30-Day Recovery — Implementation Guide

## Overview

Replace the current hard `user.delete()` with a soft delete that:
1. Marks the account as **pending deletion** with a 30-day expiry
2. Immediately locks the account (no login, no API access)
3. Sends a confirmation email with a **cancel/recover link**
4. A scheduled job permanently deletes accounts after 30 days
5. User can cancel deletion within the 30-day window via the link

---

## Edge Cases to Handle

| Scenario | Handling |
|----------|----------|
| User tries to log in during pending deletion | Return specific error: "Account scheduled for deletion. Check email to cancel." |
| User tries to register with same email during pending deletion | Block — email is still taken |
| User cancels deletion → tries to log in | Restore `is_active=True`, clear deletion fields, allow login normally |
| OAuth user (no password) deletes account | No password confirmation needed — just confirm intent |
| User requests deletion twice | Idempotent — reset the 30-day timer, resend email |
| Deletion job runs but user already cancelled | Check `scheduled_deletion_at` is still set before deleting |
| User has active sessions during pending deletion | Blacklist all refresh tokens immediately on deletion request |
| User has pending reminders on notes | Notes are preserved during grace period, deleted with account |
| User has uploaded files (avatar, note images, audio) | Must delete from storage when account is permanently deleted |
| Admin deletes user from backoffice | Bypass grace period — hard delete immediately (admin action is intentional) |
| User's email changes during grace period | Recovery email was sent to old address — recovery link uses token, not email, so still works |
| Recovery link is expired (>30 days) | Account is already deleted — return "Account no longer exists" |
| Recovery link is used after account is already permanently deleted | Same — return graceful error |
| Multiple deletion requests in quick succession (race condition) | Use `update_or_create` / atomic update to prevent duplicate scheduled deletions |
| User deletes account then tries to re-register with same email before 30 days | Block registration — email still reserved. After permanent deletion, allow re-registration |

---

## Step 1: Model Changes

### `apps/users/models.py`

Add two fields to `User`:

```python
scheduled_deletion_at = models.DateTimeField(blank=True, null=True, db_index=True)
deletion_recovery_token = models.CharField(max_length=100, blank=True, default="", db_index=True)
```

Add a property for convenience:

```python
@property
def is_pending_deletion(self) -> bool:
    return self.scheduled_deletion_at is not None
```

### Migration

```python
migrations.AddField(model_name="user", name="scheduled_deletion_at", field=models.DateTimeField(blank=True, null=True, db_index=True)),
migrations.AddField(model_name="user", name="deletion_recovery_token", field=models.CharField(max_length=100, blank=True, default="", db_index=True)),
```

---

## Step 2: Email Template

### `templates/emails/account-deletion-scheduled.html` / `.txt`

Content:
- "Your account is scheduled for permanent deletion on **{date}**"
- "If this was a mistake, click below to cancel:"
- `[Cancel Account Deletion]` → links to `{FRONTEND_URL}/auth/recover-account/{token}`
- "If you did not request this, please contact support immediately."

---

## Step 3: Backend Views

### Update `delete_account` — `apps/users/views.py`

```python
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """Schedule account for deletion in 30 days."""
    from datetime import timedelta
    user = request.user

    # Idempotent: reset timer if already pending
    token = get_random_string(64)
    user.scheduled_deletion_at = timezone.now() + timedelta(days=30)
    user.deletion_recovery_token = token
    user.is_active = False  # immediately block login
    user.save(update_fields=["scheduled_deletion_at", "deletion_recovery_token", "is_active"])

    # Blacklist all active sessions immediately
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken as RT
    for session in user.sessions.all():
        try:
            ot = OutstandingToken.objects.get(jti=session.jti)
            RT(ot.token).blacklist()
        except Exception:
            pass
    user.sessions.all().delete()

    # Send recovery email
    send_deletion_scheduled_email(user, token)

    return Response({"message": "Account scheduled for deletion in 30 days. Check your email to cancel."})
```

### New `recover_account` endpoint

```python
@api_view(["POST"])
@permission_classes([AllowAny])
def recover_account(request, token):
    """Cancel scheduled account deletion."""
    try:
        user = User.objects.get(deletion_recovery_token=token, is_active=False)
    except User.DoesNotExist:
        return Response({"error": "Invalid or expired recovery link."}, status=status.HTTP_400_BAD_REQUEST)

    if not user.scheduled_deletion_at:
        return Response({"error": "No pending deletion found."}, status=status.HTTP_400_BAD_REQUEST)

    user.scheduled_deletion_at = None
    user.deletion_recovery_token = ""
    user.is_active = True
    user.save(update_fields=["scheduled_deletion_at", "deletion_recovery_token", "is_active"])

    return Response({"message": "Account recovery successful. You can now log in."})
```

### Update login to handle pending deletion

In `CustomTokenObtainPairView` or wherever login is handled, after fetching the user:

```python
if not user.is_active and user.is_pending_deletion:
    return Response(
        {"error": "Your account is scheduled for deletion. Check your email to cancel."},
        status=status.HTTP_403_FORBIDDEN,
    )
```

---

## Step 4: Permanent Deletion Job

### Management command — `apps/users/management/commands/purge_deleted_accounts.py`

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.models import User

class Command(BaseCommand):
    help = "Permanently delete accounts past their scheduled deletion date."

    def handle(self, *args, **options):
        expired = User.objects.filter(
            scheduled_deletion_at__lte=timezone.now(),
            is_active=False,
        )
        count = expired.count()
        for user in expired:
            # Delete uploaded files from storage
            if user.avatar:
                user.avatar.delete(save=False)
            # Note files are deleted via CASCADE + Django signals (already handled in notes/signals.py)
            user.delete()
        self.stdout.write(f"Purged {count} account(s).")
```

### Schedule it

**On Render** — add to `render.yaml` as a cron job:
```yaml
- type: cron
  name: purge-deleted-accounts
  schedule: "0 2 * * *"   # daily at 2am UTC
  buildCommand: pip install -r requirements/production.txt
  startCommand: python manage.py purge_deleted_accounts
```

**Or via `django-crontab` / Celery beat** if you add a task queue later.

---

## Step 5: URLs

```python
# apps/users/urls.py
path("recover-account/<str:token>/", recover_account, name="recover_account"),
```

---

## Step 6: Frontend

### Recovery page — `pages/auth/recover-account/[token].vue`

```vue
<script setup lang="ts">
const route = useRoute()
const { request } = useApiFetch()
const success = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    await request(`/api/auth/recover-account/${route.params.token}/`, { method: 'POST' })
    success.value = true
  } catch (e: any) {
    error.value = e.message
  }
})
</script>

<template>
  <div>
    <p v-if="success">Account recovered! <NuxtLink to="/auth/login">Log in</NuxtLink></p>
    <p v-else-if="error">{{ error }}</p>
    <p v-else>Recovering your account...</p>
  </div>
</template>
```

### Update delete account flow

Show the 30-day grace period info in the confirmation dialog:
> "Your account will be permanently deleted in 30 days. You'll receive an email with a link to cancel if you change your mind."

### Add recovery page to public middleware paths

```ts
// middleware/auth.global.ts
to.path.startsWith('/auth/recover-account')
```

---

## Step 7: Admin Backoffice

Admin hard-deletes should bypass the grace period entirely — the current `user.delete()` in admin views is correct as-is. No change needed there.

Add a visual indicator in the admin user list for accounts with `scheduled_deletion_at` set.

---

## Summary of All Changes

| Layer | Change |
|-------|--------|
| Model | `scheduled_deletion_at`, `deletion_recovery_token`, `is_pending_deletion` property |
| Migration | 2 new fields |
| Email template | `account-deletion-scheduled.html/.txt` |
| `delete_account` view | Soft delete + blacklist sessions + send email |
| New `recover_account` view | Clear deletion fields, restore `is_active` |
| Login view | Handle `is_pending_deletion` case with specific error |
| Management command | `purge_deleted_accounts` — runs daily |
| Render cron | Schedule the purge command |
| Frontend | Recovery page + updated confirmation dialog + middleware public path |

---

## What NOT to Do

- Don't anonymize the user data during the grace period — it complicates recovery
- Don't send daily reminder emails during the 30 days — one email on deletion request is enough
- Don't use `is_active=False` alone to detect pending deletion — other things (admin deactivation) also set `is_active=False`. Always check `scheduled_deletion_at is not None` to distinguish
- Don't delete note files during the grace period — wait until permanent deletion
- Don't allow login with a recovery token — recovery just restores the account, user must log in normally after
