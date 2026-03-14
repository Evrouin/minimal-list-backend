from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PasswordResetToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom user admin."""

    list_display = ["email", "username", "is_verified", "is_staff", "created_at"]
    list_filter = ["is_staff", "is_superuser", "is_verified", "created_at"]
    search_fields = ["email", "username", "phone"]
    ordering = ["-created_at"]

    fieldsets = BaseUserAdmin.fieldsets + (  # type: ignore[operator]
        ("Additional Info", {"fields": ("phone", "avatar", "bio", "is_verified")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    readonly_fields = ["created_at", "updated_at"]

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2"),
            },
        ),
    )


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin for password reset tokens."""

    list_display = ["user", "token_preview", "created_at", "is_used"]
    list_filter = ["is_used", "created_at"]
    search_fields = ["user__email", "token"]
    readonly_fields = ["token", "created_at"]

    def token_preview(self, obj):
        return f"{obj.token[:20]}..."

    token_preview.short_description = "Token"  # type: ignore[attr-defined]
