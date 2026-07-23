from django.contrib.auth import authenticate, password_validation
from datetime import datetime, timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from . import models


def url_for(request, field):
    if not field:
        return None
    return request.build_absolute_uri(field.url) if request else field.url


class RegisterSerializer(serializers.Serializer):
    fullName = serializers.CharField(source="full_name", max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        if models.User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        password_validation.validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        return models.User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(email=attrs["email"], password=attrs["password"])
        if not user or user.is_deleted:
            raise serializers.ValidationError("Invalid email or password.")
        attrs["user"] = user
        return attrs


def auth_payload(user, refresh=None, access=None):
    refresh = refresh or RefreshToken.for_user(user)
    access = access or refresh.access_token
    return {
        "token": str(access),
        "refreshToken": str(refresh),
        "accessTokenExpiresAt": datetime.fromtimestamp(access["exp"], timezone.utc).isoformat(),
        "refreshTokenExpiresAt": datetime.fromtimestamp(refresh["exp"], timezone.utc).isoformat(),
        "fullName": user.full_name,
        "email": user.email,
        "roles": ["Admin"] if user.is_staff else ["User"],
    }


class UserProfileSerializer(serializers.ModelSerializer):
    fullName = serializers.CharField(source="full_name")
    phoneNumber = serializers.CharField(source="phone_number", allow_blank=True, allow_null=True, required=False)
    imageUrl = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = models.User
        fields = ("id", "fullName", "email", "phoneNumber", "imageUrl", "roles")
        read_only_fields = ("id", "email", "imageUrl", "roles")

    def get_imageUrl(self, obj):
        return url_for(self.context.get("request"), obj.image)

    def get_roles(self, obj):
        return ["Admin"] if obj.is_staff else ["User"]


class PublicUserSerializer(serializers.ModelSerializer):
    fullName = serializers.CharField(source="full_name")
    phoneNumber = serializers.SerializerMethodField()
    imageUrl = serializers.SerializerMethodField()
    isVerified = serializers.BooleanField(source="is_verified")
    isPhoneVerified = serializers.BooleanField(source="is_phone_verified")

    class Meta:
        model = models.User
        fields = ("id", "fullName", "phoneNumber", "imageUrl", "isVerified", "isPhoneVerified")

    def get_phoneNumber(self, obj):
        return None if obj.hide_phone_number else obj.phone_number

    def get_imageUrl(self, obj):
        return url_for(self.context.get("request"), obj.image)


class MasterDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BodyType
        fields = ("id", "name")


class CarModelMasterSerializer(serializers.ModelSerializer):
    carBrandId = serializers.IntegerField(source="brand_id")
    carBrandName = serializers.CharField(source="brand.name")

    class Meta:
        model = models.CarModel
        fields = ("id", "name", "carBrandId", "carBrandName")


class CarSummarySerializer(serializers.ModelSerializer):
    brand = serializers.CharField(source="brand.name")
    model = serializers.CharField(source="model.name")
    condition = serializers.CharField(source="condition.name")
    transmission = serializers.CharField(source="transmission.name")
    fuelType = serializers.CharField(source="fuel_type.name")
    listedDate = serializers.DateTimeField(source="listed_date")
    mainImageUrl = serializers.SerializerMethodField()
    moderationReason = serializers.CharField(source="moderation_reason", allow_null=True)

    class Meta:
        model = models.Car
        fields = (
            "id", "title", "price", "status", "brand", "model", "condition", "year", "mileage",
            "transmission", "fuelType", "city", "listedDate", "mainImageUrl", "moderationReason",
        )

    def get_mainImageUrl(self, obj):
        image = next((item for item in obj.images.all() if item.is_main), None)
        image = image or next(iter(obj.images.all()), None)
        return url_for(self.context.get("request"), image.image) if image else None


class CarDetailsSerializer(serializers.ModelSerializer):
    brand = serializers.CharField(source="brand.name")
    model = serializers.CharField(source="model.name")
    listedDate = serializers.DateTimeField(source="listed_date")
    bodyType = serializers.CharField(source="body_type.name")
    condition = serializers.CharField(source="condition.name")
    transmission = serializers.CharField(source="transmission.name")
    fuelType = serializers.CharField(source="fuel_type.name")
    engineSize = serializers.CharField(source="engine_size")
    reviewCount = serializers.IntegerField(source="review_count")
    seller = PublicUserSerializer()
    images = serializers.SerializerMethodField()
    features = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    vehicleHistories = serializers.SerializerMethodField()

    class Meta:
        model = models.Car
        fields = (
            "id", "title", "price", "status", "brand", "model", "rating", "reviewCount", "views",
            "listedDate", "bodyType", "condition", "mileage", "transmission", "year", "fuelType",
            "color", "doors", "cylinders", "engineSize", "vin", "description", "city", "address",
            "seller", "images", "features", "vehicleHistories",
        )

    def get_images(self, obj):
        request = self.context.get("request")
        return [url_for(request, item.image) for item in obj.images.all()]

    def get_vehicleHistories(self, obj):
        return [item.description for item in obj.vehicle_histories.all()]


class CarWriteSerializer(serializers.ModelSerializer):
    carBrandId = serializers.PrimaryKeyRelatedField(source="brand", queryset=models.CarBrand.objects.all())
    carModelId = serializers.PrimaryKeyRelatedField(source="model", queryset=models.CarModel.objects.all())
    bodyTypeId = serializers.PrimaryKeyRelatedField(source="body_type", queryset=models.BodyType.objects.all())
    carConditionId = serializers.PrimaryKeyRelatedField(source="condition", queryset=models.CarCondition.objects.all())
    transmissionId = serializers.PrimaryKeyRelatedField(source="transmission", queryset=models.Transmission.objects.all())
    fuelTypeId = serializers.PrimaryKeyRelatedField(source="fuel_type", queryset=models.FuelType.objects.all())
    featureIds = serializers.PrimaryKeyRelatedField(source="features", queryset=models.Feature.objects.all(), many=True, required=False)
    engineSize = serializers.CharField(source="engine_size", required=False, allow_blank=True)

    class Meta:
        model = models.Car
        fields = (
            "title", "carBrandId", "carModelId", "price", "bodyTypeId", "carConditionId", "mileage",
            "year", "transmissionId", "fuelTypeId", "city", "featureIds", "address", "description",
            "color", "doors", "cylinders", "engineSize", "vin",
        )

    def validate(self, attrs):
        if attrs["model"].brand_id != attrs["brand"].id:
            raise serializers.ValidationError({"carModelId": "The model does not belong to the selected brand."})
        return attrs


class ReviewSerializer(serializers.ModelSerializer):
    reviewerId = serializers.IntegerField(source="reviewer_id")
    reviewerName = serializers.CharField(source="reviewer.full_name")
    reviewerImageUrl = serializers.SerializerMethodField()
    sellerId = serializers.IntegerField(source="seller_id")
    createdAt = serializers.DateTimeField(source="created_at")
    moderationReason = serializers.CharField(source="moderation_reason", allow_null=True)

    class Meta:
        model = models.Review
        fields = ("id", "rating", "comment", "createdAt", "reviewerId", "reviewerName", "reviewerImageUrl", "sellerId", "status", "moderationReason")

    def get_reviewerImageUrl(self, obj):
        return url_for(self.context.get("request"), obj.reviewer.image)


class ReviewWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Review
        fields = ("rating", "comment")


class ChatSerializer(serializers.ModelSerializer):
    carId = serializers.IntegerField(source="car_id")
    carTitle = serializers.CharField(source="car.title")
    otherUserId = serializers.SerializerMethodField()
    otherUserName = serializers.SerializerMethodField()
    otherUserImageUrl = serializers.SerializerMethodField()
    otherUserIsVerified = serializers.SerializerMethodField()
    otherUserIsPhoneVerified = serializers.SerializerMethodField()
    otherUserIsOnline = serializers.SerializerMethodField()
    otherUserLastSeenAt = serializers.SerializerMethodField()
    lastMessage = serializers.SerializerMethodField()
    lastMessageAt = serializers.SerializerMethodField()
    unreadCount = serializers.SerializerMethodField()

    class Meta:
        model = models.Chat
        fields = ("id", "carId", "carTitle", "otherUserId", "otherUserName", "otherUserImageUrl",
                  "otherUserIsVerified", "otherUserIsPhoneVerified", "otherUserIsOnline",
                  "otherUserLastSeenAt", "lastMessage", "lastMessageAt", "unreadCount")

    def other(self, obj):
        user = self.context["request"].user
        return obj.seller if user.id == obj.buyer_id else obj.buyer

    def get_otherUserId(self, obj): return self.other(obj).id
    def get_otherUserName(self, obj): return self.other(obj).full_name
    def get_otherUserImageUrl(self, obj): return url_for(self.context.get("request"), self.other(obj).image)
    def get_otherUserIsVerified(self, obj): return self.other(obj).is_verified
    def get_otherUserIsPhoneVerified(self, obj): return self.other(obj).is_phone_verified
    def get_otherUserIsOnline(self, obj): return False
    def get_otherUserLastSeenAt(self, obj): return None
    def get_lastMessage(self, obj):
        last = obj.messages.last()
        return last.content if last else None
    def get_lastMessageAt(self, obj):
        last = obj.messages.last()
        return last.sent_at if last else None
    def get_unreadCount(self, obj):
        return obj.messages.filter(is_read=False).exclude(sender=self.context["request"].user).count()


class MessageSerializer(serializers.ModelSerializer):
    chatId = serializers.IntegerField(source="chat_id")
    senderId = serializers.IntegerField(source="sender_id")
    senderName = serializers.CharField(source="sender.full_name")
    sentAt = serializers.DateTimeField(source="sent_at")
    isRead = serializers.BooleanField(source="is_read")

    class Meta:
        model = models.Message
        fields = ("id", "chatId", "senderId", "senderName", "content", "sentAt", "isRead")


class ContactMessageSerializer(serializers.ModelSerializer):
    carId = serializers.IntegerField(source="car_id", read_only=True)
    phoneNumber = serializers.CharField(source="phone_number", required=False, allow_blank=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    isRead = serializers.BooleanField(source="is_read", read_only=True)

    class Meta:
        model = models.ContactMessage
        fields = ("id", "carId", "name", "email", "subject", "phoneNumber", "message", "createdAt", "isRead")


class VehicleHistorySerializer(serializers.ModelSerializer):
    serviceDate = serializers.DateField(source="service_date", required=False, allow_null=True)
    recordType = serializers.CharField(source="record_type", required=False)
    documentUrl = serializers.URLField(source="document_url", required=False, allow_null=True, allow_blank=True)
    carId = serializers.IntegerField(source="car_id", read_only=True)

    class Meta:
        model = models.VehicleHistory
        fields = ("id", "carId", "description", "serviceDate", "mileage", "provider", "cost", "recordType", "documentUrl")


class ReportSerializer(serializers.ModelSerializer):
    targetType = serializers.CharField(source="target_type")
    targetId = serializers.IntegerField(source="target_id")
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    resolutionNote = serializers.CharField(source="resolution_note", read_only=True, allow_null=True)

    class Meta:
        model = models.Report
        fields = ("id", "targetType", "targetId", "reason", "details", "status", "createdAt", "resolutionNote")
        read_only_fields = ("id", "status")


class NotificationSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source="user_id")
    relatedEntityType = serializers.CharField(source="related_entity_type", allow_null=True)
    relatedEntityId = serializers.IntegerField(source="related_entity_id", allow_null=True)
    actionUrl = serializers.CharField(source="action_url", allow_null=True)
    isRead = serializers.BooleanField(source="is_read")
    createdAt = serializers.DateTimeField(source="created_at")
    readAt = serializers.DateTimeField(source="read_at", allow_null=True)

    class Meta:
        model = models.Notification
        fields = ("id", "userId", "type", "title", "message", "relatedEntityType", "relatedEntityId", "actionUrl", "isRead", "createdAt", "readAt")


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    eventType = serializers.CharField(source="event_type")
    isEnabled = serializers.BooleanField(source="is_enabled")

    class Meta:
        model = models.NotificationPreference
        fields = ("eventType", "isEnabled")


class NotificationPreferencesRequestSerializer(serializers.Serializer):
    preferences = NotificationPreferenceSerializer(many=True)


class SellerCarImageSerializer(serializers.ModelSerializer):
    imageUrl = serializers.SerializerMethodField()
    thumbnailUrl = serializers.SerializerMethodField()
    isMain = serializers.BooleanField(source="is_main")
    displayOrder = serializers.IntegerField(source="display_order")
    processingStatus = serializers.SerializerMethodField()
    processingError = serializers.SerializerMethodField()
    processingAttempts = serializers.SerializerMethodField()

    class Meta:
        model = models.CarImage
        fields = ("id", "imageUrl", "thumbnailUrl", "isMain", "displayOrder", "processingStatus", "processingError", "processingAttempts")

    def get_imageUrl(self, obj): return url_for(self.context.get("request"), obj.image)
    def get_thumbnailUrl(self, obj): return url_for(self.context.get("request"), obj.thumbnail)
    def get_processingStatus(self, obj): return obj.processing_status
    def get_processingError(self, obj): return obj.processing_error
    def get_processingAttempts(self, obj): return obj.processing_attempts


class ModerationHistorySerializer(serializers.ModelSerializer):
    carId = serializers.IntegerField(source="car_id")
    adminUserId = serializers.IntegerField(source="admin_user_id")
    adminName = serializers.CharField(source="admin_user.full_name")
    previousStatus = serializers.CharField(source="previous_status")
    newStatus = serializers.CharField(source="new_status")
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = models.ModerationHistory
        fields = ("id", "carId", "adminUserId", "adminName", "previousStatus", "newStatus", "reason", "createdAt")


class ModerationCarSerializer(serializers.ModelSerializer):
    sellerId = serializers.IntegerField(source="seller_id")
    sellerName = serializers.CharField(source="seller.full_name")
    brand = serializers.CharField(source="brand.name")
    model = serializers.CharField(source="model.name")
    listedDate = serializers.DateTimeField(source="listed_date")
    moderationReason = serializers.CharField(source="moderation_reason", allow_null=True)
    moderatedAt = serializers.DateTimeField(source="moderated_at", allow_null=True)
    moderatedByUserId = serializers.IntegerField(source="moderated_by_id", allow_null=True)
    images = serializers.SerializerMethodField()

    class Meta:
        model = models.Car
        fields = ("id", "title", "status", "sellerId", "sellerName", "brand", "model", "price",
                  "listedDate", "moderationReason", "moderatedAt", "moderatedByUserId",
                  "description", "city", "vin", "year", "mileage", "images")

    def get_images(self, obj):
        return [url_for(self.context.get("request"), image.image) for image in obj.images.all()]


class AuditLogSerializer(serializers.ModelSerializer):
    actorUserId = serializers.IntegerField(source="actor_id", allow_null=True)
    actorName = serializers.CharField(source="actor.full_name", allow_null=True)
    entityType = serializers.CharField(source="entity_type")
    entityId = serializers.CharField(source="entity_id", allow_null=True)
    ipAddress = serializers.IPAddressField(source="ip_address", allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = models.AuditLog
        fields = ("id", "actorUserId", "actorName", "action", "entityType", "entityId", "details", "ipAddress", "createdAt")


class DeadLetterEventSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id")
    occurredAt = serializers.DateTimeField(source="created_at")
    deadLetteredAt = serializers.DateTimeField(source="dead_lettered_at")
    lastError = serializers.CharField(source="last_error", allow_null=True)

    class Meta:
        model = models.RealtimeOutboxEvent
        fields = ("id", "occurredAt", "attempts", "deadLetteredAt", "lastError")


class SavedSearchSerializer(serializers.ModelSerializer):
    carBrandId = serializers.PrimaryKeyRelatedField(source="brand", queryset=models.CarBrand.objects.all(), allow_null=True, required=False)
    carModelId = serializers.PrimaryKeyRelatedField(source="model", queryset=models.CarModel.objects.all(), allow_null=True, required=False)
    minPrice = serializers.DecimalField(source="min_price", max_digits=12, decimal_places=2, allow_null=True, required=False)
    maxPrice = serializers.DecimalField(source="max_price", max_digits=12, decimal_places=2, allow_null=True, required=False)
    notifyNewListings = serializers.BooleanField(source="notify_new_listings", required=False)
    notifyPriceDrops = serializers.BooleanField(source="notify_price_drops", required=False)
    notifySold = serializers.BooleanField(source="notify_sold", required=False)
    isEnabled = serializers.BooleanField(source="is_enabled", required=False)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = models.SavedSearch
        fields = ("id", "name", "carBrandId", "carModelId", "minPrice", "maxPrice", "city",
                  "notifyNewListings", "notifyPriceDrops", "notifySold", "isEnabled", "createdAt", "updatedAt")


class SettingsSerializer(serializers.ModelSerializer):
    enableMessages = serializers.BooleanField(source="enable_messages")
    receiveEmailNotifications = serializers.BooleanField(source="receive_email_notifications")
    hidePhoneNumber = serializers.BooleanField(source="hide_phone_number")
    receiveMessageNotifications = serializers.BooleanField(source="receive_message_notifications")
    isProfilePrivate = serializers.BooleanField(source="is_profile_private")

    class Meta:
        model = models.User
        fields = ("enableMessages", "receiveEmailNotifications", "hidePhoneNumber", "receiveMessageNotifications", "isProfilePrivate")


# Command serializers make non-CRUD request bodies explicit in OpenAPI/Swagger.
class RefreshTokenRequestSerializer(serializers.Serializer):
    refreshToken = serializers.CharField(required=False, allow_blank=True, help_text="Optional when the HttpOnly refresh cookie is present.")


class ChangePasswordRequestSerializer(serializers.Serializer):
    currentPassword = serializers.CharField()
    newPassword = serializers.CharField(min_length=8)
    confirmNewPassword = serializers.CharField(min_length=8)


class ProfileImageRequestSerializer(serializers.Serializer):
    file = serializers.ImageField()


class CreateChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)


class SendMessageRequestSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=2000)


class CloseAccountRequestSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=("NoLongerNeeded", "PrivacyConcerns", "TooManyNotifications", "BadExperience", "Other"))
    details = serializers.CharField(required=False, allow_blank=True)


class SellerStatusRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("Available", "Reserved", "Sold", "Inactive"))


class ListingDraftRequestSerializer(serializers.Serializer):
    payload = serializers.JSONField()
    step = serializers.IntegerField(min_value=1, default=1)


class ModerateCarRequestSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=("Approve", "Reject"))
    reason = serializers.CharField(required=False, allow_blank=True)


class ModerateReportRequestSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=("Resolve", "Dismiss"))
    note = serializers.CharField(required=False, allow_blank=True)


class ModerateReviewRequestSerializer(serializers.Serializer):
    decision = serializers.CharField(help_text="Approve/Reject (the legacy Angular client may also send 1/0).")
    reason = serializers.CharField(required=False, allow_blank=True)
