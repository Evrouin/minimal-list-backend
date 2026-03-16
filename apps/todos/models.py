from django.conf import settings
from django.db import models


class Todo(models.Model):
    """Todo item belonging to a user."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="todos")
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="todos/", blank=True, null=True)
    completed = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "todos"
        ordering = ["-pinned", "-created_at"]

    def __str__(self):
        return self.title
