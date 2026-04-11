# User Deactivation Feature — Implementation Guide

## Overview

Deactivation is a **reversible, non-destructive** account suspension — distinct from deletion.

| | Deactivation | Soft Deletion |
|--|-------------|---------------|
| Data preserved | ✅ | ✅ (30-day grace) |
| Can log in | ❌ | ❌ |
| Self-service recovery | ✅ (reactivate anytime) | ✅ (within 30 days) |
| Notes preserved | ✅ | ✅ (until permanent delete) |
| Initiated by | User or Admin | User or Admin |
| Permanent | ❌ | ✅ (after 30 days) |

---

## What Already Exists

- `is_active` field on `User` model ✅
- Admin can toggle `is_active` via `PATCH /api/admin/users/:id/` ✅
- Login already checks `is_active` and returns `"Your account has been deactivated. Please contact support."` ✅
- Google OAuth login also checks `is_active` ✅

**What's missing:**
- Self-service deactivation endpoint for users
- Self-service reactivation (currently no way for a user to reactivate themselves)
- Distinguishing admin-deactivated vs self-deactivated (important for the error message and recovery flow)
- Session blacklisting on deactivation
- Email notification on deactivation/reactivation

---

## Edge Cases

| Scenario | Handling |
|----------|----------|
| Deactivated user tries to log in | Return specific error based on `deactivation_reason`: self-deactivated → show reactivation link; admin-deactivated → "contact support" |
| User deactivates then tries to reactivate immediately | Allow — no cooldown needed |
| Admin deactivates a user who self-deactivated | Admin wins — `deactivation_reason = "admin"`, user cannot self-reactivate |
| Admin reactivates a user | Clear `deactivation_reason`, restore `is_active=True` |
| User deactivates account while having pending deletion scheduled | Cancel the deletion, deactivate instead (deactivation is less destructive) |
| OAuth user deactivates | No password needed — just confirm intent |
| User tries to register with a deactivated account's email | Block — email is still taken |
| Deactivated user's sessions | Blacklist all refresh tokens immediately |
| User reactivates → old sessions | Sessions were deleted on deactivation — user must log in fresh |
| Admin deactivates superuser | Prevent self-demotion; allow deactivating other admins only if requester is also superuser |
| Reactivation email link expires | Link is token-based with 7-day expiry — after expiry, user must contact support or use the login page reactivation flow |

---

## Step 1: Model Changes

### `apps/users/models.py`

Add two fields to `User`:

```python
deactivation_reason = models.CharField(
    max_length=10,
    choices=[("self", "Self"), ("admin", "Admin")],
    blank=True,
    default="",
)
reactivation_token = models.CharField(max_length=100, blank=True, default="", db_index=True)
reactivation_token_expires = models.DateTimeField(blank=True, null=True)
```

Add a property:

```python
@property
def is_self_deactivated(self) -> bool:
    return not self.is_active and self.deactivation_reason == "self"

@property
def is_admin_deactivated(self) -> bool:
    return not self.is_active and self.deactivation_reason == "admin"
```

### Migration

```python
migrations.AddField(model_name="user", name="deactivation_reason", field=models.CharField(max_length=10, blank=True, default="")),
migrations.AddField(model_name="user", name="reactivation_token", field=models.CharField(max_length=100, blank=True, default="", db_index=True)),
migrations.AddField(model_name="user", name="reactivation_token_expires", field=models.DateTimeField(blank=True, null=True)),
```

---

## Step 2: Email Templates

### `templates/emails/account-deactivated.html/.txt`
- "Your account has been deactivated."
- If self-deactivated: include `[Reactivate My Account]` button → `{FRONTEND_URL}/auth/reactivate/{token}`
- If admin-deactivated: "Please contact support if you believe this is a mistake."

### `templates/emails/account-reactivated.html/.txt`
- "Your account has been reactivated. You can now log in."

---

## Step 3: Backend Views

### Self-service deactivation — `apps/users/views.py`

```python
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def deactivate_account(request):
    """Self-service account deactivation."""
    from datetime import timedelta
    user = request.user

    # If pending deletion, cancel it
    if user.scheduled_deletion_at:
        user.scheduled_deletion_at = None
        user.deletion_recovery_token = ""

    token = get_random_string(64)
    user.is_active = False
    user.deactivation_reason = "self"
    user.reactivation_token = token
    user.reactivation_token_expires = timezone.now() + timedelta(days=7)
    user.save(update_fields=[
        "is_active", "deactivation_reason", "reactivation_token",
        "reactivation_token_expires", "scheduled_deletion_at", "deletion_recovery_token"
    ])

    # Blacklist all sessions
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken as RT
    for session in user.sessions.all():
        try:
            ot = OutstandingToken.objects.get(jti=session.jti)
            RT(ot.token).blacklist()
        except Exception:
            pass
    user.sessions.all().delete()

    send_account_deactivated_email(user, token, reason="self")

    return Response({"message": "Account deactivated. Check your email to reactivate."})
```

### Self-service reactivation

```python
@api_view(["POST"])
@permission_classes([AllowAny])
def reactivate_account(request, token):
    """Reactivate a self-deactivated account via token."""
    try:
        user = User.objects.get(
            reactivation_token=token,
            deactivation_reason="self",
            is_active=False,
        )
    except User.DoesNotExist:
        return Response({"error": "Invalid or expired reactivation link."}, status=status.HTTP_400_BAD_REQUEST)

    if user.reactivation_token_expires and user.reactivation_token_expires < timezone.now():
        return Response({"error": "Reactivation link has expired. Please contact support."}, status=status.HTTP_400_BAD_REQUEST)

    user.is_active = True
    user.deactivation_reason = ""
    user.reactivation_token = ""
    user.reactivation_token_expires = None
    user.save(update_fields=["is_active", "deactivation_reason", "reactivation_token", "reactivation_token_expires"])

    send_account_reactivated_email(user)

    return Response({"message": "Account reactivated. You can now log in."})
```

### Update login error message

In the login view, replace the generic `is_active` check with a context-aware message:

```python
if not user.is_active:
    if user.deactivation_reason == "self":
        return Response(
            {"error": "Your account is deactivated. Check your email for a reactivation link."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return Response(
        {"error": "Your account has been deactivated. Please contact support."},
        status=status.HTTP_403_FORBIDDEN,
    )
```

Apply the same to `google_login` (and future GitHub/LinkedIn login views).

### Update admin deactivation

Override `partial_update` in `AdminUserDetailView` to handle `is_active` changes:

```python
def partial_update(self, request, *args, **kwargs):
    user = self.get_object()
    is_active = request.data.get("is_active")

    if is_active is False and user.is_active:
        # Admin deactivating
        user.deactivation_reason = "admin"
        user.reactivation_token = ""
        user.reactivation_token_expires = None
        user.save(update_fields=["deactivation_reason", "reactivation_token", "reactivation_token_expires"])
        # Blacklist sessions
        for session in user.sessions.all():
            try:
                ot = OutstandingToken.objects.get(jti=session.jti)
                RefreshToken(ot.token).blacklist()
            except Exception:
                pass
        user.sessions.all().delete()
        send_account_deactivated_email(user, token=None, reason="admin")

    elif is_active is True and not user.is_active:
        # Admin reactivating
        user.deactivation_reason = ""
        user.reactivation_token = ""
        user.reactivation_token_expires = None
        user.save(update_fields=["deactivation_reason", "reactivation_token", "reactivation_token_expires"])
        send_account_reactivated_email(user)

    return super().partial_update(request, *args, **kwargs)
```

---

## Step 4: URLs

```python
# apps/users/urls.py
path("deactivate/", deactivate_account, name="deactivate_account"),
path("reactivate/<str:token>/", reactivate_account, name="reactivate_account"),
```

---

## Step 5: Frontend

### Deactivation — `pages/auth/profile.vue`

Add a "Deactivate Account" section (separate from Delete Account):

```ts
const deactivateAccount = async () => {
  await api.deactivateAccount()
  authStore.clearAuth()
  navigateTo('/auth/login')
}
```

```ts
// composables/useAuthApi.ts
deactivateAccount: () =>
  request(`${base}/deactivate/`, { method: 'POST' }),
```

### Reactivation page — `pages/auth/reactivate/[token].vue`

```vue
<script setup lang="ts">
const route = useRoute()
const { request } = useApiFetch()
const success = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    await request(`/api/auth/reactivate/${route.params.token}/`, { method: 'POST' })
    success.value = true
  } catch (e: any) {
    error.value = e.message
  }
})
</script>

<template>
  <div>
    <p v-if="success">Account reactivated! <NuxtLink to="/auth/login">Log in</NuxtLink></p>
    <p v-else-if="error">{{ error }}</p>
    <p v-else>Reactivating your account...</p>
  </div>
</template>
```

### Login page — show reactivation hint

If login returns the self-deactivated error message, show a note:
> "Check your email for a reactivation link, or request a new one below."

Optionally add a "Resend reactivation email" button that calls a new endpoint.

### Middleware — add public path

```ts
to.path.startsWith('/auth/reactivate')
```

---

## Summary of All Changes

| Layer | Change |
|-------|--------|
| Model | `deactivation_reason`, `reactivation_token`, `reactivation_token_expires` + properties |
| Migration | 3 new fields |
| Email templates | `account-deactivated.html/.txt`, `account-reactivated.html/.txt` |
| `deactivate_account` view | New — self-service, blacklists sessions, sends email |
| `reactivate_account` view | New — token-based, validates expiry |
| Login views | Context-aware error message (self vs admin deactivation) |
| `AdminUserDetailView` | Override `partial_update` to handle session blacklisting + emails on `is_active` toggle |
| URLs | 2 new endpoints |
| Frontend API | `deactivateAccount()` method |
| Frontend pages | Reactivation page + deactivate button in profile |
| Middleware | Add `/auth/reactivate` to public paths |

---

## What NOT to Do

- Don't allow self-reactivation for admin-deactivated accounts — only admins can reactivate those
- Don't reuse the same token field as account deletion recovery — keep `reactivation_token` and `deletion_recovery_token` separate to avoid collision
- Don't send a reactivation email for admin-deactivated users — they should contact support, not self-serve
- Don't hide deactivated users from the admin panel — show them with a clear "Deactivated" badge
