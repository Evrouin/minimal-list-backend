from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.crypto import get_random_string


class User(AbstractUser):
    """Custom user model with additional fields."""

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True, default="")
    is_verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=100, blank=True, default="")
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
        """Create a new password reset token."""
        token = get_random_string(64)
        return cls.objects.create(user=user, token=token)

    def is_valid(self):
        """Check if token is still valid (24 hours)."""
        from datetime import timedelta

        from django.utils import timezone

        return not self.is_used and (timezone.now() - self.created_at) < timedelta(hours=24)
