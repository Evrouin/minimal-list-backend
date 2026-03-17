from rest_framework import serializers

from .models import Todo
from .utils import process_image

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB


class TodoSerializer(serializers.ModelSerializer):
    """Serializer for todo items."""

    class Meta:
        model = Todo
        fields = ["id", "title", "body", "image", "thumbnail", "completed", "deleted", "pinned", "created_at", "updated_at"]
        read_only_fields = ["id", "thumbnail", "created_at", "updated_at"]

    def validate_image(self, value):
        if value and value.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError("Image must be under 5MB.")
        return value

    def create(self, validated_data):
        image = validated_data.get("image")
        if image:
            validated_data["image"], validated_data["thumbnail"] = process_image(image)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        image = validated_data.get("image")
        if image:
            validated_data["image"], validated_data["thumbnail"] = process_image(image)
        return super().update(instance, validated_data)
