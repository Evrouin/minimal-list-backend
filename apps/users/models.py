import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils.crypto import get_random_string
from django.utils import timezone


class User(AbstractUser):
    """Custom user model with additional fields."""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    avatar_url = models.URLField(blank=True, default="")
    bio = models.TextField(blank=True, default="")
    is_verified = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)
    verification_token = models.CharField(max_length=100, blank=True, default="", db_index=True)
    # Deactivation
    deactivation_reason = models.CharField(max_length=10, choices=[("self", "Self"), ("admin", "Admin")], blank=True, default="")
    reactivation_token = models.CharField(max_length=100, blank=True, default="", db_index=True)
    reactivation_token_expires = models.DateTimeField(blank=True, null=True)
    # Soft deletion
    scheduled_deletion_at = models.DateTimeField(blank=True, null=True, db_index=True)
    deletion_recovery_token = models.CharField(max_length=100, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email

    def generate_verification_token(self):
        """Generate a unique verification token."""
        self.verification_token = get_random_string(64)
        self.save()
        return self.verification_token

    @property
    def is_self_deactivated(self) -> bool:
        return not self.is_active and self.deactivation_reason == "self"

    @property
    def is_admin_deactivated(self) -> bool:
        return not self.is_active and self.deactivation_reason == "admin"

    @property
    def is_pending_deletion(self) -> bool:
        return self.scheduled_deletion_at is not None


class PasswordResetToken(models.Model):
    """Password reset tokens."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "password_reset_tokens"

    def __str__(self):
        return f"{self.user.email} - {self.token[:10]}..."

    @classmethod
    def create_token(cls, user):
        """Create a new password reset token and clean up expired ones."""
        from datetime import timedelta

        from django.utils import timezone

        cls.objects.filter(
            Q(created_at__lt=timezone.now() - timedelta(hours=24)) | Q(is_used=True)
        ).delete()
        token = get_random_string(64)
        return cls.objects.create(user=user, token=token)

    def is_valid(self):
        """Check if token is still valid (24 hours)."""
        from datetime import timedelta

        from django.utils import timezone

        return not self.is_used and (timezone.now() - self.created_at) < timedelta(hours=24)


class UserSession(models.Model):
    """Tracks active user sessions linked to JWT refresh tokens."""

    DEVICE_TYPES = [("desktop", "Desktop"), ("mobile", "Mobile"), ("tablet", "Tablet"), ("unknown", "Unknown")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions")
    jti = models.CharField(max_length=255, unique=True)
    device_name = models.CharField(max_length=255, default="Unknown device")
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES, default="unknown")
    browser = models.CharField(max_length=100, default="")
    os = models.CharField(max_length=100, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(default="")
    device_fingerprint = models.CharField(max_length=255, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_sessions"
        ordering = ["-last_active_at"]

    def __str__(self):
        return f"{self.user.email} - {self.device_name}"

    @classmethod
    def create_from_request(cls, user, jti, request):
        from user_agents import parse

        ua_string = request.META.get("HTTP_USER_AGENT", "")
        ua = parse(ua_string)
        browser = f"{ua.browser.family} {ua.browser.version_string}".strip()
        os = f"{ua.os.family} {ua.os.version_string}".strip()
        if ua.is_mobile:
            device_type = "mobile"
        elif ua.is_tablet:
            device_type = "tablet"
        elif ua.is_pc:
            device_type = "desktop"
        else:
            device_type = "unknown"
        device_name = f"{browser} on {os}" if browser and os else ua_string[:100] or "Unknown device"
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")

        device_fingerprint = f"{ip}:{browser}:{os}:{device_type}"

        existing_session = cls.objects.filter(
            user=user,
            device_fingerprint=device_fingerprint
        ).first()

        if existing_session:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            try:
                old_token = OutstandingToken.objects.get(jti=existing_session.jti)
                from rest_framework_simplejwt.tokens import RefreshToken
                RefreshToken(old_token.token).blacklist()
            except Exception:
                pass

            existing_session.jti = jti
            existing_session.last_active_at = timezone.now()
            existing_session.save()
            return existing_session
        else:
            return cls.objects.create(
                user=user, jti=jti, device_name=device_name, device_type=device_type,
                browser=browser, os=os, ip_address=ip, user_agent=ua_string,
                device_fingerprint=device_fingerprint,
            )
