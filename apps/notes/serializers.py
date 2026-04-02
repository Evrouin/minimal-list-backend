from rest_framework import serializers

from .models import Note
from .utils import process_image

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/ogg", "audio/x-m4a"}


class NoteSerializer(serializers.ModelSerializer):
    """Serializer for note items."""

    class Meta:
        model = Note
        fields = ["id", "title", "body", "image", "thumbnail", "audio", "link_previews", "completed", "deleted", "pinned", "color", "reminder_at", "created_at", "updated_at"]
        read_only_fields = ["id", "thumbnail", "created_at", "updated_at"]

    def validate_image(self, value):
        if value and value.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError("Image must be under 5MB.")
        return value

    def validate_audio(self, value):
        if value:
            if value.size > MAX_AUDIO_SIZE:
                raise serializers.ValidationError("Audio must be under 10MB.")
            if value.content_type not in ALLOWED_AUDIO_TYPES:
                raise serializers.ValidationError("Unsupported audio format.")
        return value

    def validate_link_previews(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Must be a list.")
        if len(value) > 10:
            raise serializers.ValidationError("Maximum 10 link previews per note.")
        required = {"url", "title", "domain"}
        allowed = {"url", "title", "description", "image", "domain"}
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each preview must be an object.")
            if not required.issubset(item.keys()):
                raise serializers.ValidationError(f"Each preview must have: {', '.join(required)}.")
            if not set(item.keys()).issubset(allowed):
                raise serializers.ValidationError(f"Allowed fields: {', '.join(allowed)}.")
            for field in allowed:
                if field in item and not isinstance(item[field], str):
                    raise serializers.ValidationError(f"'{field}' must be a string.")
        return value

    def create(self, validated_data):
        image = validated_data.get("image")
        if image:
            validated_data["image"], validated_data["thumbnail"] = process_image(image)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        old_image_name = instance.image.name if instance.image else None
        old_thumbnail_name = instance.thumbnail.name if instance.thumbnail else None
        old_image_storage = instance.image.storage if instance.image else None
        old_thumbnail_storage = instance.thumbnail.storage if instance.thumbnail else None
        old_audio_name = instance.audio.name if instance.audio else None
        old_audio_storage = instance.audio.storage if instance.audio else None

        if "image" in validated_data:
            image = validated_data.get("image")
            if image:
                validated_data["image"], validated_data["thumbnail"] = process_image(image)
            else:
                validated_data["thumbnail"] = None

        updated = super().update(instance, validated_data)

        if "image" in validated_data:
            new_image_name = updated.image.name if updated.image else None
            new_thumbnail_name = updated.thumbnail.name if updated.thumbnail else None

            if old_image_name and old_image_name != new_image_name and old_image_storage:
                old_image_storage.delete(old_image_name)
            if old_thumbnail_name and old_thumbnail_name != new_thumbnail_name and old_thumbnail_storage:
                old_thumbnail_storage.delete(old_thumbnail_name)

        if "audio" in validated_data:
            new_audio_name = updated.audio.name if updated.audio else None
            if old_audio_name and old_audio_name != new_audio_name and old_audio_storage:
                old_audio_storage.delete(old_audio_name)

        return updated
