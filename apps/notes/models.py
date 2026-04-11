import uuid

from django.conf import settings
from django.db import models


class Folder(models.Model):
    """Folder for organizing notes. Three default folders are seeded per user."""

    DEFAULT_FOLDERS = ["notes", "tasks", "reminders"]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="folders")
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "folders"
        ordering = ["-is_default", "order", "created_at"]
        indexes = [
            models.Index(fields=["user", "is_archived"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="unique_folder_name_per_user"),
        ]

    def __str__(self):
        return f"{self.user_id} / {self.name}"


class Note(models.Model):
    """Note item belonging to a user."""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notes")
    folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name="notes")
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="notes/", blank=True, null=True)
    thumbnail = models.ImageField(upload_to="notes/thumbs/", blank=True, null=True)
    audio = models.FileField(upload_to="notes/audio/", blank=True, null=True)
    link_previews = models.JSONField(blank=True, default=list)
    completed = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    archived_by_folder = models.BooleanField(default=False)  # True when archived as part of a folder archive
    order_id = models.BigIntegerField(default=0)
    color = models.CharField(max_length=20, default="default")
    reminder_at = models.DateTimeField(blank=True, null=True)
    snoozed_until = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notes"
        ordering = ["-pinned", "-order_id", "-created_at"]
        indexes = [
            models.Index(fields=["user", "deleted"]),
            models.Index(fields=["user", "is_archived"]),
            models.Index(fields=["user", "-pinned", "-order_id"]),
        ]

    def __str__(self):
        return self.title
