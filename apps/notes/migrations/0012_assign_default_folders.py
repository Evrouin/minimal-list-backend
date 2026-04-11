from django.db import migrations


def assign_folders(apps, schema_editor):
    Note = apps.get_model("notes", "Note")
    Folder = apps.get_model("notes", "Folder")
    User = apps.get_model("users", "User")

    # Seed default folders for any user that doesn't have them yet
    for i, name in enumerate(["notes", "tasks", "reminders"]):
        for user in User.objects.all():
            Folder.objects.get_or_create(user=user, name=name, defaults={"is_default": True, "order": i})

    # Assign notes with reminder_at → reminders folder
    for folder in Folder.objects.filter(is_default=True, name="reminders"):
        Note.objects.filter(user=folder.user, folder__isnull=True, reminder_at__isnull=False).update(folder=folder)

    # Assign remaining unassigned notes → notes folder
    for folder in Folder.objects.filter(is_default=True, name="notes"):
        Note.objects.filter(user=folder.user, folder__isnull=True).update(folder=folder)


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0011_merge_20260411_0417"),
    ]

    operations = [
        migrations.RunPython(assign_folders, migrations.RunPython.noop),
    ]
