from django.db.models import Max
from rest_framework import serializers

from .models import Folder, Note
from .utils import process_image


class FolderSerializer(serializers.ModelSerializer):
    note_count = serializers.SerializerMethodField()

    class Meta:
        model = Folder
        fields = ["uuid", "name", "is_default", "order", "is_archived", "note_count", "created_at"]
        read_only_fields = ["uuid", "is_default", "is_archived", "created_at"]

    def get_note_count(self, obj):
        if hasattr(obj, "active_note_count"):
            return obj.active_note_count
        return obj.notes.filter(deleted=False, is_archived=False).count()

    def validate_name(self, value):
        user = self.context["request"].user
        qs = Folder.objects.filter(user=user, name=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A folder with this name already exists.")
        return value

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/ogg", "audio/x-m4a"}


class NoteSerializer(serializers.ModelSerializer):
    """Serializer for note items."""

    folder = serializers.SlugRelatedField(slug_field="uuid", queryset=Folder.objects.none(), allow_null=True, required=False)

    class Meta:
        model = Note
        fields = ["uuid", "folder", "title", "body", "image", "thumbnail", "audio", "link_previews", "completed", "deleted", "pinned", "is_archived", "archived_by_folder", "order_id", "color", "reminder_at", "snoozed_until", "created_at", "updated_at"]
        read_only_fields = ["uuid", "thumbnail", "is_archived", "archived_by_folder", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["folder"].queryset = Folder.objects.filter(user=request.user)

    def validate_order_id(self, value):
        if value is None or not isinstance(value, int) or value < 0:
            raise serializers.ValidationError("order_id must be a non-negative integer.")
        return value

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

        if "order_id" not in validated_data:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if user and user.is_authenticated:
                from django.db.models import F, Min

                if validated_data.get("pinned"):
                    max_order = Note.objects.filter(user=user, deleted=False).aggregate(max_order=Max("order_id"))["max_order"] or 0
                    validated_data["order_id"] = max_order + 1
                else:
                    pinned_min = Note.objects.filter(user=user, deleted=False, pinned=True).aggregate(m=Min("order_id"))["m"]
                    if pinned_min:
                        validated_data["order_id"] = pinned_min
                        Note.objects.filter(user=user, deleted=False, pinned=True).update(order_id=F("order_id") + 1)
                    else:
                        max_order = Note.objects.filter(user=user, deleted=False).aggregate(max_order=Max("order_id"))["max_order"] or 0
                        validated_data["order_id"] = max_order + 1

        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "pinned" in validated_data and validated_data["pinned"] != instance.pinned:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if user and user.is_authenticated:
                from django.db.models import F, Min

                if validated_data["pinned"]:
                    max_order = Note.objects.filter(user=user, deleted=False).aggregate(m=Max("order_id"))["m"] or 0
                    validated_data["order_id"] = max_order + 1
                else:
                    pinned_min = Note.objects.filter(user=user, deleted=False, pinned=True).exclude(pk=instance.pk).aggregate(m=Min("order_id"))["m"]
                    if pinned_min:
                        validated_data["order_id"] = pinned_min
                        Note.objects.filter(user=user, deleted=False, pinned=True).exclude(pk=instance.pk).update(order_id=F("order_id") + 1)
                    else:
                        max_order = Note.objects.filter(user=user, deleted=False).exclude(pk=instance.pk).aggregate(m=Max("order_id"))["m"] or 0
                        validated_data["order_id"] = max_order + 1

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
