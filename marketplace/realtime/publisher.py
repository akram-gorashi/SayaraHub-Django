from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone
from marketplace import models


def dispatch_event(event_id):
    with transaction.atomic():
        event = models.RealtimeOutboxEvent.objects.select_for_update().filter(
            id=event_id, processed_at__isnull=True, dead_lettered_at__isnull=True
        ).first()
        if not event:
            return
        try:
            async_to_sync(get_channel_layer().group_send)(
                event.group_name, {"type": "realtime.event", "payload": event.payload}
            )
            event.processed_at = timezone.now()
            event.attempts += 1
            event.last_error = None
        except Exception as exc:
            event.attempts += 1
            event.last_error = str(exc)[:2000]
            if event.attempts >= 10:
                event.dead_lettered_at = timezone.now()
        event.save(update_fields=["processed_at", "dead_lettered_at", "attempts", "last_error"])


def enqueue_event(group_name, event_type, payload):
    event = models.RealtimeOutboxEvent.objects.create(
        group_name=group_name, event_type=event_type, payload={"type": event_type, **payload}
    )
    transaction.on_commit(lambda: dispatch_event(event.id))
    return event
