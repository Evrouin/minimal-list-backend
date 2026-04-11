import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models import Folder, Note

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def seed_default_folders(sender, instance, created, **kwargs):
    """Seed the three default folders for new users (and existing users missing them)."""
    for i, name in enumerate(Folder.DEFAULT_FOLDERS):
        Folder.objects.get_or_create(
            user=instance,
            name=name,
            defaults={"is_default": True, "order": i},
        )


@receiver(pre_delete, sender=Note)
def delete_note_files(sender, instance: Note, **kwargs):
    """Remove Note image objects from storage on permanent delete."""
    for field_name in ("image", "thumbnail", "audio"):
        field = getattr(instance, field_name, None)
        if not field or not getattr(field, "name", None):
            continue
        try:
            field.storage.delete(field.name)
        except Exception:
            logger.exception("Failed deleting %s for Note id=%s", field_name, instance.pk)
