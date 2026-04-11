from django.db import migrations, models


def add_archived_by_folder(apps, schema_editor):
    """Add archived_by_folder column only if it doesn't already exist."""
    from django.db import connection
    cols = [col.name for col in connection.introspection.get_table_description(connection.cursor(), "notes")]
    if "archived_by_folder" not in cols:
        schema_editor.add_field(
            apps.get_model("notes", "Note"),
            models.BooleanField(default=False, name="archived_by_folder"),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0008_add_folder_and_archived"),
    ]

    operations = [
        migrations.RunPython(add_archived_by_folder, migrations.RunPython.noop),
    ]
