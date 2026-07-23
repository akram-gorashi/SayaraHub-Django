import uuid
from django.db import migrations, models


def populate_unique_public_ids(apps, schema_editor):
    Outbox = apps.get_model("marketplace", "RealtimeOutboxEvent")
    for event in Outbox.objects.all().iterator():
        event.public_id = uuid.uuid4()
        event.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0004_carimage_processing_attempts_and_more")]

    operations = [
        migrations.RunPython(populate_unique_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="realtimeoutboxevent",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
