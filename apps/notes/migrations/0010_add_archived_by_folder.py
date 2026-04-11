from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notes", "0008_add_folder_and_archived"),
    ]

    operations = [
        migrations.AddField(
            model_name="note",
            name="archived_by_folder",
            field=models.BooleanField(default=False),
        ),
    ]
