from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0007_alter_note_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Create Folder table
        migrations.CreateModel(
            name="Folder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="folders", to=settings.AUTH_USER_MODEL)),
                ("name", models.CharField(max_length=100)),
                ("is_default", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_archived", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "folders", "ordering": ["-is_default", "order", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="folder",
            constraint=models.UniqueConstraint(fields=["user", "name"], name="unique_folder_name_per_user"),
        ),
        migrations.AddIndex(
            model_name="folder",
            index=models.Index(fields=["user", "is_archived"], name="folders_user_archived_idx"),
        ),
        # Add folder FK and is_archived to Note
        migrations.AddField(
            model_name="note",
            name="folder",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notes", to="notes.folder"),
        ),
        migrations.AddField(
            model_name="note",
            name="is_archived",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="note",
            index=models.Index(fields=["user", "is_archived"], name="notes_user_archived_idx"),
        ),
    ]
