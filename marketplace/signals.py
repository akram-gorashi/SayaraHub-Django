from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db import transaction
from . import models
from .realtime.publisher import enqueue_event
from .serializers import MessageSerializer, NotificationSerializer


@receiver(post_save, sender=models.Message)
def publish_message(sender, instance, created, **kwargs):
    if not created:
        return
    enqueue_event(
        f"chat_{instance.chat_id}",
        "message.received",
        {"message": MessageSerializer(instance).data},
    )
    recipient = instance.chat.seller if instance.sender_id == instance.chat.buyer_id else instance.chat.buyer
    if recipient.receive_message_notifications:
        models.Notification.objects.create(
            user=recipient,
            type="ChatMessage",
            title=f"New message from {instance.sender.full_name}",
            message=instance.content[:250],
            related_entity_type="Chat",
            related_entity_id=instance.chat_id,
            action_url="/account/messages",
        )


@receiver(post_save, sender=models.Notification)
def publish_notification(sender, instance, created, **kwargs):
    if created:
        disabled = models.NotificationPreference.objects.filter(
            user_id=instance.user_id, event_type=instance.type, is_enabled=False
        ).exists()
        if disabled:
            instance.delete()
            return
        enqueue_event(
            f"user_{instance.user_id}",
            "notification.received",
            {"notification": NotificationSerializer(instance).data},
        )
        if instance.user.receive_email_notifications:
            from .tasks import send_notification_email
            transaction.on_commit(lambda: send_notification_email.delay(
                instance.user_id, instance.title, instance.message
            ))


@receiver(post_save, sender=models.ContactMessage)
def notify_contact_inquiry(sender, instance, created, **kwargs):
    if created:
        models.Notification.objects.create(
            user=instance.seller,
            type="ContactInquiry",
            title=f"New inquiry about {instance.car.title}",
            message=instance.message[:250],
            related_entity_type="ContactMessage",
            related_entity_id=instance.id,
            action_url="/account/inquiries",
        )


@receiver(post_save, sender=models.CarImage)
def queue_image_processing(sender, instance, created, **kwargs):
    if created and instance.processing_status == "Pending":
        from .tasks import process_car_image
        transaction.on_commit(lambda: process_car_image.delay(instance.id))


@receiver(pre_save, sender=models.Car)
def remember_car_status(sender, instance, **kwargs):
    previous = models.Car.objects.filter(id=instance.id).values("status", "price").first() if instance.id else None
    instance._previous_status = previous["status"] if previous else None
    instance._previous_price = previous["price"] if previous else None


@receiver(post_save, sender=models.Car)
def notify_pending_listing(sender, instance, created, **kwargs):
    became_pending = instance.status == models.Car.Status.PENDING and (
        created or getattr(instance, "_previous_status", None) != models.Car.Status.PENDING
    )
    if became_pending:
        for admin in models.User.objects.filter(is_staff=True, is_active=True):
            models.Notification.objects.create(
                user=admin,
                type="ListingPendingReview",
                title="Listing requires moderation",
                message=f'"{instance.title}" was submitted for review.',
                related_entity_type="Car",
                related_entity_id=instance.id,
                action_url=f"/admin/moderation/{instance.id}",
            )

    became_available = instance.status == models.Car.Status.AVAILABLE and (
        created or getattr(instance, "_previous_status", None) != models.Car.Status.AVAILABLE
    )
    price_dropped = (
        instance.status == models.Car.Status.AVAILABLE
        and getattr(instance, "_previous_price", None) is not None
        and instance.price < instance._previous_price
    )
    became_sold = instance.status == models.Car.Status.SOLD and getattr(instance, "_previous_status", None) != models.Car.Status.SOLD
    if not (became_available or price_dropped or became_sold):
        return
    searches = models.SavedSearch.objects.select_related("user").filter(is_enabled=True).exclude(user_id=instance.seller_id)
    searches = searches.filter(
        models.Q(brand__isnull=True) | models.Q(brand_id=instance.brand_id),
        models.Q(model__isnull=True) | models.Q(model_id=instance.model_id),
        models.Q(min_price__isnull=True) | models.Q(min_price__lte=instance.price),
        models.Q(max_price__isnull=True) | models.Q(max_price__gte=instance.price),
        models.Q(city__isnull=True) | models.Q(city__iexact=instance.city),
    )
    for search in searches:
        event_type = None
        if became_available and search.notify_new_listings:
            event_type = "SavedSearchNewListing"
        elif price_dropped and search.notify_price_drops:
            event_type = "SavedSearchPriceDrop"
        elif became_sold and search.notify_sold:
            event_type = "SavedSearchSold"
        if event_type:
            models.Notification.objects.create(
                user=search.user, type=event_type, title=search.name,
                message=f'Update for "{instance.title}".', related_entity_type="Car",
                related_entity_id=instance.id, action_url=f"/cars/{instance.id}",
            )
