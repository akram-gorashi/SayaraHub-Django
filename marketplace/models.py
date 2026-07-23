from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
import uuid


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    image = models.ImageField(upload_to="profiles/", blank=True, null=True)
    phone_number = models.CharField(max_length=32, blank=True, null=True)
    enable_messages = models.BooleanField(default=True)
    receive_email_notifications = models.BooleanField(default=False)
    hide_phone_number = models.BooleanField(default=False)
    receive_message_notifications = models.BooleanField(default=True)
    is_profile_private = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)
    deletion_reason = models.CharField(max_length=64, blank=True, null=True)
    deletion_details = models.TextField(blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]
    objects = UserManager()


class NamedModel(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class BodyType(NamedModel):
    pass


class CarBrand(NamedModel):
    pass


class CarModel(NamedModel):
    name = models.CharField(max_length=100)
    brand = models.ForeignKey(CarBrand, related_name="models", on_delete=models.CASCADE)

    class Meta(NamedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["brand", "name"], name="unique_brand_model")]


class CarCondition(NamedModel):
    pass


class Feature(NamedModel):
    pass


class FuelType(NamedModel):
    pass


class Transmission(NamedModel):
    pass


class Car(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending"
        AVAILABLE = "Available"
        REJECTED = "Rejected"
        RESERVED = "Reserved"
        SOLD = "Sold"
        INACTIVE = "Inactive"

    title = models.CharField(max_length=200)
    brand = models.ForeignKey(CarBrand, on_delete=models.PROTECT)
    model = models.ForeignKey(CarModel, on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    rating = models.FloatField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    views = models.PositiveIntegerField(default=0)
    listed_date = models.DateTimeField(auto_now_add=True, db_index=True)
    body_type = models.ForeignKey(BodyType, on_delete=models.PROTECT)
    condition = models.ForeignKey(CarCondition, on_delete=models.PROTECT)
    mileage = models.PositiveIntegerField(default=0)
    transmission = models.ForeignKey(Transmission, on_delete=models.PROTECT)
    year = models.PositiveSmallIntegerField()
    fuel_type = models.ForeignKey(FuelType, on_delete=models.PROTECT)
    color = models.CharField(max_length=50, blank=True)
    doors = models.PositiveSmallIntegerField(default=4)
    cylinders = models.PositiveSmallIntegerField(default=4)
    engine_size = models.CharField(max_length=30, blank=True)
    vin = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100, db_index=True)
    address = models.CharField(max_length=250, blank=True)
    seller = models.ForeignKey(User, related_name="cars", on_delete=models.CASCADE)
    features = models.ManyToManyField(Feature, blank=True)
    moderation_reason = models.TextField(blank=True, null=True)
    moderated_at = models.DateTimeField(blank=True, null=True)
    moderated_by = models.ForeignKey(User, related_name="+", blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-listed_date", "-id"]
        indexes = [models.Index(fields=["status", "city", "price"])]


class CarImage(models.Model):
    car = models.ForeignKey(Car, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="cars/")
    thumbnail = models.ImageField(upload_to="cars/thumbnails/", blank=True, null=True)
    is_main = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)
    processing_status = models.CharField(max_length=20, default="Pending", db_index=True)
    processing_error = models.TextField(blank=True, null=True)
    processing_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]


class CarView(models.Model):
    car = models.ForeignKey(Car, related_name="view_records", on_delete=models.CASCADE)
    visitor_key = models.CharField(max_length=80)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["car", "visitor_key"], name="unique_car_visitor")]


class Favorite(models.Model):
    user = models.ForeignKey(User, related_name="favorites", on_delete=models.CASCADE)
    car = models.ForeignKey(Car, related_name="favorites", on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "car"], name="unique_favorite")]


class Review(models.Model):
    class Status(models.TextChoices):
        PENDING = "Pending"
        APPROVED = "Approved"
        REJECTED = "Rejected"

    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewer = models.ForeignKey(User, related_name="reviews_given", on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name="reviews_received", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    moderation_reason = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["reviewer", "seller"], name="unique_seller_review"),
            models.CheckConstraint(condition=~Q(reviewer=models.F("seller")), name="no_self_review"),
        ]


class Chat(models.Model):
    car = models.ForeignKey(Car, related_name="chats", on_delete=models.CASCADE)
    buyer = models.ForeignKey(User, related_name="buyer_chats", on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name="seller_chats", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["car", "buyer"], name="unique_car_buyer_chat")]


class Message(models.Model):
    chat = models.ForeignKey(Chat, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name="sent_messages", on_delete=models.CASCADE)
    content = models.CharField(max_length=2000)
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["sent_at", "id"]


class ContactMessage(models.Model):
    car = models.ForeignKey(Car, related_name="contact_messages", on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name="contact_messages", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=32, blank=True, null=True)
    message = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)


class VehicleHistory(models.Model):
    car = models.ForeignKey(Car, related_name="vehicle_histories", on_delete=models.CASCADE)
    description = models.CharField(max_length=1000)
    service_date = models.DateField(blank=True, null=True)
    mileage = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=150, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    record_type = models.CharField(max_length=40, default="Service")
    document_url = models.URLField(blank=True, null=True)


class UserBlock(models.Model):
    blocker = models.ForeignKey(User, related_name="blocks_created", on_delete=models.CASCADE)
    blocked_user = models.ForeignKey(User, related_name="blocks_received", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["blocker", "blocked_user"], name="unique_user_block")]


class Report(models.Model):
    reporter = models.ForeignKey(User, related_name="reports", on_delete=models.CASCADE)
    target_type = models.CharField(max_length=20)
    target_id = models.PositiveBigIntegerField()
    reason = models.CharField(max_length=100)
    details = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, default="Open")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(User, related_name="+", blank=True, null=True, on_delete=models.SET_NULL)
    resolution_note = models.TextField(blank=True, null=True)


class Notification(models.Model):
    user = models.ForeignKey(User, related_name="notifications", on_delete=models.CASCADE)
    type = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_entity_type = models.CharField(max_length=50, blank=True, null=True)
    related_entity_id = models.PositiveBigIntegerField(blank=True, null=True)
    action_url = models.CharField(max_length=250, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)


class NotificationPreference(models.Model):
    user = models.ForeignKey(User, related_name="notification_preferences", on_delete=models.CASCADE)
    event_type = models.CharField(max_length=60)
    is_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "event_type"], name="unique_notification_preference")]


class SavedSearch(models.Model):
    user = models.ForeignKey(User, related_name="saved_searches", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    brand = models.ForeignKey(CarBrand, blank=True, null=True, on_delete=models.SET_NULL)
    model = models.ForeignKey(CarModel, blank=True, null=True, on_delete=models.SET_NULL)
    min_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    max_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    notify_new_listings = models.BooleanField(default=True)
    notify_price_drops = models.BooleanField(default=True)
    notify_sold = models.BooleanField(default=True)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CarListingDraft(models.Model):
    user = models.OneToOneField(User, related_name="listing_draft", on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    step = models.PositiveSmallIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class ModerationHistory(models.Model):
    car = models.ForeignKey(Car, related_name="moderation_history", on_delete=models.CASCADE)
    admin_user = models.ForeignKey(User, related_name="+", on_delete=models.PROTECT)
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    actor = models.ForeignKey(User, related_name="+", blank=True, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=80, blank=True, null=True)
    details = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class UserRealtimePresence(models.Model):
    user = models.OneToOneField(User, related_name="realtime_presence", on_delete=models.CASCADE)
    connection_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(blank=True, null=True)


class RealtimeOutboxEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    group_name = models.CharField(max_length=120)
    event_type = models.CharField(max_length=60)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(blank=True, null=True, db_index=True)
    dead_lettered_at = models.DateTimeField(blank=True, null=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, null=True)
