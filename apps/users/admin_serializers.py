from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.todos.models import Todo

User = get_user_model()


class AdminTodoSerializer(serializers.ModelSerializer):
    """Todo serializer with user info for admin views."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Todo
        fields = [
            "id",
            "title",
            "body",
            "image",
            "completed",
            "deleted",
            "pinned",
            "user_email",
            "username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AdminCreateUserSerializer(serializers.ModelSerializer):
    """Serializer for admin user creation."""

    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["email", "username", "password", "is_superuser", "is_verified"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
