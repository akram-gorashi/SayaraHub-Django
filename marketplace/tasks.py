from celery import shared_task
from . import models
from .realtime.publisher import dispatch_event
from django.core.mail import send_mail
from django.core.files.base import ContentFile
from PIL import Image
from io import BytesIO
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import socket
import struct


@shared_task(name="marketplace.dispatch_realtime_outbox")
def dispatch_realtime_outbox():
    ids = list(
        models.RealtimeOutboxEvent.objects.filter(
            processed_at__isnull=True, dead_lettered_at__isnull=True, attempts__lt=10
        )
        .order_by("created_at").values_list("id", flat=True)[:200]
    )
    for event_id in ids:
        dispatch_event(event_id)
    return len(ids)


@shared_task(name="marketplace.send_notification_email", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def send_notification_email(user_id, title, message):
    user = models.User.objects.filter(id=user_id, is_active=True, receive_email_notifications=True).first()
    if not user:
        return False
    send_mail(title, message, None, [user.email], fail_silently=False)
    return True


@shared_task(name="marketplace.process_car_image", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_car_image(image_id):
    item = models.CarImage.objects.get(id=image_id)
    item.processing_status = "Processing"
    item.processing_attempts += 1
    item.processing_error = None
    item.save(update_fields=["processing_status", "processing_attempts", "processing_error"])
    try:
        if settings.CLAMAV_HOST:
            with item.image.open("rb") as source, socket.create_connection(
                (settings.CLAMAV_HOST, settings.CLAMAV_PORT), timeout=15
            ) as scanner:
                scanner.sendall(b"zINSTREAM\0")
                while chunk := source.read(64 * 1024):
                    scanner.sendall(struct.pack("!I", len(chunk)) + chunk)
                scanner.sendall(struct.pack("!I", 0))
                result = scanner.recv(4096).decode(errors="replace")
                if "FOUND" in result:
                    raise ValueError("Malware was detected in the uploaded image.")
                if "OK" not in result:
                    raise RuntimeError(f"ClamAV scan failed: {result}")
        elif settings.CLAMAV_REQUIRED:
            raise RuntimeError("ClamAV is required but is not configured.")
        with item.image.open("rb") as source:
            image = Image.open(source)
            image.verify()
        with item.image.open("rb") as source:
            image = Image.open(source)
            image.load()
            if image.width * image.height > 50_000_000:
                raise ValueError("Image dimensions are too large.")
            image = image.convert("RGB")
            image.thumbnail((1920, 1920))
            output = BytesIO()
            image.save(output, format="WEBP", quality=85, method=6)
            item.image.save(f"{item.id}.webp", ContentFile(output.getvalue()), save=False)
            thumb = image.copy()
            thumb.thumbnail((480, 360))
            thumbnail = BytesIO()
            thumb.save(thumbnail, format="WEBP", quality=78, method=6)
            item.thumbnail.save(f"{item.id}_thumb.webp", ContentFile(thumbnail.getvalue()), save=False)
        item.processing_status = "Completed"
        item.save(update_fields=["image", "thumbnail", "processing_status"])
    except Exception as exc:
        item.processing_status = "Failed"
        item.processing_error = str(exc)[:2000]
        item.save(update_fields=["processing_status", "processing_error"])
        raise


@shared_task(name="marketplace.cleanup_stale_presence")
def cleanup_stale_presence():
    cutoff = timezone.now() - timedelta(seconds=90)
    return models.UserRealtimePresence.objects.filter(
        connection_count__gt=0, updated_at__lt=cutoff
    ).update(connection_count=0, last_seen_at=timezone.now())
