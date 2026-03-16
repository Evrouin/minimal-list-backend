from rest_framework import serializers

from .models import Todo


class TodoSerializer(serializers.ModelSerializer):
    """Serializer for todo items."""

    class Meta:
        model = Todo
        fields = ["id", "title", "body", "image", "completed", "deleted", "pinned", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
