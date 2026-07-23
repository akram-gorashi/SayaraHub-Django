from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import password_validation
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.db import transaction
from django.db.models import Avg, Count, DateTimeField, F, OuterRef, Q, Subquery, Sum
from django.http import JsonResponse
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
import csv
import secrets
from datetime import timedelta
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from PIL import Image, UnidentifiedImageError
from rest_framework import permissions, serializers as drf_serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView as DRFAPIView
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from . import models, serializers
from .responses import fail, ok, page
from .realtime.publisher import enqueue_event


class EmptySerializer(drf_serializers.Serializer):
    pass


class APIView(DRFAPIView):
    serializer_class = EmptySerializer


def health(request):
    return JsonResponse({"status": "Healthy"})


def health_ready(request):
    checks = {"database": False, "redis": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        pass
    try:
        key = f"health:{secrets.token_hex(8)}"
        cache.set(key, "ok", timeout=5)
        checks["redis"] = cache.get(key) == "ok"
        cache.delete(key)
    except Exception:
        pass
    healthy = all(checks.values())
    return JsonResponse({"status": "Healthy" if healthy else "Unhealthy", "checks": checks}, status=200 if healthy else 503)


def metrics(request):
    if request.headers.get("X-Metrics-Key") != settings.METRICS_KEY:
        return HttpResponse(status=403)
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


def participant_or_404(user, chat_id):
    return get_object_or_404(
        models.Chat.objects.select_related("car", "buyer", "seller"),
        Q(buyer=user) | Q(seller=user), id=chat_id,
    )


def owned_car_or_404(user, car_id):
    query = models.Car.objects.all() if user.is_staff else models.Car.objects.filter(seller=user)
    return get_object_or_404(query, id=car_id)


def write_audit(request, action, entity_type, entity_id=None, details=None):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    models.AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details, ip_address=ip,
    )


def validate_image_upload(file, max_bytes=10 * 1024 * 1024):
    if file.size > max_bytes:
        raise DRFValidationError(f"Image must not exceed {max_bytes // (1024 * 1024)} MB.")
    try:
        Image.open(file).verify()
        file.seek(0)
    except (UnidentifiedImageError, OSError):
        raise DRFValidationError("The uploaded file is not a valid image.")


class AuthRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.RegisterSerializer
    throttle_scope = "auth"

    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response = ok(serializers.auth_payload(user), "Registration successful", status.HTTP_201_CREATED)
        response.set_cookie("refreshToken", response.data["data"]["refreshToken"], httponly=True, secure=not settings.DEBUG, samesite="Lax", max_age=604800)
        return response


class AuthLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.LoginSerializer
    throttle_scope = "auth"

    def post(self, request):
        serializer = serializers.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = ok(serializers.auth_payload(serializer.validated_data["user"]), "Login successful")
        response.set_cookie("refreshToken", response.data["data"]["refreshToken"], httponly=True, secure=not settings.DEBUG, samesite="Lax", max_age=604800)
        return response


class AuthRefreshView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.RefreshTokenRequestSerializer
    throttle_scope = "auth"

    def post(self, request):
        token = request.data.get("refreshToken") or request.COOKIES.get("refreshToken")
        serializer = TokenRefreshSerializer(data={"refresh": token})
        serializer.is_valid(raise_exception=True)
        rotated = serializer.validated_data.get("refresh", token)
        refresh = RefreshToken(rotated)
        user = get_object_or_404(models.User, id=refresh["sub"], is_active=True)
        access = refresh.access_token
        response = ok(serializers.auth_payload(user, refresh=refresh, access=access))
        response.set_cookie("refreshToken", str(refresh), httponly=True, secure=not settings.DEBUG, samesite="Lax", max_age=604800)
        return response


class AuthRevokeView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.RefreshTokenRequestSerializer

    def post(self, request):
        token = request.data.get("refreshToken") or request.COOKIES.get("refreshToken")
        if not token:
            return fail("refreshToken is required.")
        try:
            RefreshToken(token).blacklist()
        except Exception:
            return fail("Invalid refresh token.")
        response = ok(message="Session revoked")
        response.delete_cookie("refreshToken")
        return response


class AuthRevokeAllView(APIView):
    def post(self, request):
        for token in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=token)
        response = ok(message="All sessions revoked")
        response.delete_cookie("refreshToken")
        return response


class AuthSessionsView(APIView):
    def get(self, request):
        cookie = request.COOKIES.get("refreshToken")
        current_jti = None
        if cookie:
            try:
                current_jti = RefreshToken(cookie)["jti"]
            except Exception:
                pass
        items = [{
            "id": str(token.id),
            "deviceName": "Web browser",
            "browser": "Unknown",
            "ipAddress": None,
            "createdAt": token.created_at,
            "lastActivityAt": token.created_at,
            "expiresAt": token.expires_at,
            "isCurrent": token.jti == current_jti,
        } for token in OutstandingToken.objects.filter(user=request.user).exclude(blacklistedtoken__isnull=False).order_by("-created_at")]
        return ok(items)


class AuthSessionDetailView(APIView):
    def delete(self, request, session_id):
        token = get_object_or_404(OutstandingToken, id=session_id, user=request.user)
        current = False
        cookie = request.COOKIES.get("refreshToken")
        if cookie:
            try:
                current = RefreshToken(cookie)["jti"] == token.jti
            except Exception:
                pass
        BlacklistedToken.objects.get_or_create(token=token)
        response = ok({"currentSessionRevoked": current})
        if current:
            response.delete_cookie("refreshToken")
        return response


class AuthRevokeOtherSessionsView(APIView):
    def post(self, request):
        cookie = request.COOKIES.get("refreshToken")
        current_jti = RefreshToken(cookie)["jti"] if cookie else None
        for token in OutstandingToken.objects.filter(user=request.user).exclude(jti=current_jti):
            BlacklistedToken.objects.get_or_create(token=token)
        return ok(message="Other sessions revoked")


class WebSocketTicketView(APIView):
    def post(self, request):
        ticket = secrets.token_urlsafe(32)
        ttl = settings.WEBSOCKET_TICKET_TTL_SECONDS
        cache.set(f"ws-ticket:{ticket}", request.user.id, timeout=ttl)
        return ok({"ticket": ticket, "expiresAt": (timezone.now() + timedelta(seconds=ttl)).isoformat()})


class UserMeView(APIView):
    serializer_class = serializers.UserProfileSerializer
    def get(self, request):
        return ok(serializers.UserProfileSerializer(request.user, context={"request": request}).data)

    def put(self, request):
        serializer = serializers.UserProfileSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(serializer.data, "Profile updated")


class PublicUserView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.PublicUserSerializer

    def get(self, request, user_id):
        user = get_object_or_404(models.User, id=user_id, is_deleted=False)
        if user.is_profile_private and request.user.id != user.id:
            return fail("This profile is private.", status=403)
        return ok(serializers.PublicUserSerializer(user, context={"request": request}).data)


class ChangePasswordView(APIView):
    serializer_class = serializers.ChangePasswordRequestSerializer
    def put(self, request):
        current = request.data.get("currentPassword")
        new = request.data.get("newPassword")
        if new != request.data.get("confirmNewPassword"):
            return fail("New passwords do not match.")
        if not request.user.check_password(current):
            return fail("Current password is incorrect.")
        try:
            password_validation.validate_password(new, request.user)
        except DjangoValidationError as exc:
            return fail(" ".join(exc.messages))
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        write_audit(request, "PasswordChanged", "User", request.user.id)
        return ok(message="Password changed")


class UserImageView(APIView):
    parser_classes = [MultiPartParser]
    serializer_class = serializers.ProfileImageRequestSerializer

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return fail("file is required.")
        validate_image_upload(file, 5 * 1024 * 1024)
        request.user.image = file
        request.user.save(update_fields=["image"])
        return ok({"imageUrl": request.build_absolute_uri(request.user.image.url)}, "Image updated")

    def delete(self, request):
        if request.user.image:
            request.user.image.delete(save=False)
            request.user.image = None
            request.user.save(update_fields=["image"])
        return ok(message="Image removed")


MASTER_MODELS = {
    "body-types": (models.BodyType, serializers.MasterDataSerializer),
    "car-brands": (models.CarBrand, serializers.MasterDataSerializer),
    "car-models": (models.CarModel, serializers.CarModelMasterSerializer),
    "car-conditions": (models.CarCondition, serializers.MasterDataSerializer),
    "features": (models.Feature, serializers.MasterDataSerializer),
    "fuel-types": (models.FuelType, serializers.MasterDataSerializer),
    "transmissions": (models.Transmission, serializers.MasterDataSerializer),
}


class MasterDataListView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.MasterDataSerializer

    def get(self, request, kind=None):
        if kind:
            model, serializer = MASTER_MODELS[kind]
            query = model.objects.all()
            name = request.query_params.get("name")
            if name:
                query = query.filter(name__icontains=name)
            return ok(page(request, query, serializer))
        data = {}
        keys = {
            "bodyTypes": "body-types", "carBrands": "car-brands", "carModels": "car-models",
            "carConditions": "car-conditions", "features": "features",
            "fuelTypes": "fuel-types", "transmissions": "transmissions",
        }
        for output, key in keys.items():
            model, serializer = MASTER_MODELS[key]
            data[output] = page(request, model.objects.all(), serializer)
        return ok(data)


class BrandModelsView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.CarModelMasterSerializer

    def get(self, request, brand_id):
        return ok(page(request, models.CarModel.objects.filter(brand_id=brand_id), serializers.CarModelMasterSerializer))


def car_queryset(include_details=False):
    query = models.Car.objects.select_related(
        "brand", "model", "body_type", "condition", "transmission", "fuel_type", "seller"
    ).prefetch_related("images")
    if include_details:
        query = query.prefetch_related("features", "vehicle_histories")
    return query


def normalized_car_data(request):
    data = request.data.copy()
    if hasattr(data, "getlist"):
        feature_ids = data.getlist("featureIds") or data.getlist("FeatureIds")
        if feature_ids:
            data.setlist("featureIds", feature_ids)
    return data


class CarListCreateView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = serializers.CarWriteSerializer

    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == "GET" else [permissions.IsAuthenticated()]

    def get(self, request):
        query = car_queryset().filter(status=models.Car.Status.AVAILABLE)
        search = request.query_params.get("search")
        if search:
            query = query.filter(Q(title__icontains=search) | Q(brand__name__icontains=search) | Q(model__name__icontains=search))
        mappings = {
            "brandIds": "brand_id__in", "modelIds": "model_id__in", "transmissionIds": "transmission_id__in",
            "fuelTypeIds": "fuel_type_id__in", "featureIds": "features__id__in",
        }
        for key, lookup in mappings.items():
            values = request.query_params.getlist(key) or request.query_params.getlist(f"{key}[]")
            if values:
                query = query.filter(**{lookup: values})
        ranges = {"minPrice": "price__gte", "maxPrice": "price__lte", "minYear": "year__gte", "maxYear": "year__lte"}
        for key, lookup in ranges.items():
            if request.query_params.get(key):
                query = query.filter(**{lookup: request.query_params[key]})
        if request.query_params.get("city"):
            query = query.filter(city__iexact=request.query_params["city"])
        sort = {"price": "price", "year": "year", "mileage": "mileage", "listedDate": "listed_date"}.get(
            request.query_params.get("sortBy"), "listed_date"
        )
        if request.query_params.get("sortDirection", "desc") == "desc":
            sort = f"-{sort}"
        return ok(page(request, query.distinct().order_by(sort, "-id"), serializers.CarSummarySerializer))

    @transaction.atomic
    def post(self, request):
        data = normalized_car_data(request)
        serializer = serializers.CarWriteSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        car = serializer.save(seller=request.user, status=models.Car.Status.PENDING)
        files = request.FILES.getlist("images") or request.FILES.getlist("Images")
        for file in files:
            validate_image_upload(file)
        main_index = int(request.data.get("mainImageIndex", request.data.get("MainImageIndex", 0)) or 0)
        for index, file in enumerate(files):
            models.CarImage.objects.create(car=car, image=file, display_order=index, is_main=index == main_index)
        return ok(serializers.CarDetailsSerializer(car, context={"request": request}).data, "Car created", status.HTTP_201_CREATED)


class CarDetailView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    serializer_class = serializers.CarWriteSerializer

    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == "GET" else [permissions.IsAuthenticated()]

    def get(self, request, car_id):
        car = get_object_or_404(car_queryset(include_details=True), id=car_id)
        if car.status != models.Car.Status.AVAILABLE and (not request.user.is_authenticated or (request.user.id != car.seller_id and not request.user.is_staff)):
            return fail("Car not found.", status=404)
        visitor_key = f"user:{request.user.id}" if request.user.is_authenticated else request.COOKIES.get("sayarahub.visitor")
        created_cookie = False
        if not visitor_key:
            visitor_key = f"anon:{secrets.token_urlsafe(24)}"
            created_cookie = True
        if request.user.id != car.seller_id:
            _, created = models.CarView.objects.get_or_create(car=car, visitor_key=visitor_key)
            if created:
                models.Car.objects.filter(id=car.id).update(views=F("views") + 1)
                car.refresh_from_db(fields=["views"])
        response = ok(serializers.CarDetailsSerializer(car, context={"request": request}).data)
        if created_cookie:
            response.set_cookie("sayarahub.visitor", visitor_key, httponly=True, samesite="Lax", secure=not settings.DEBUG, max_age=31536000)
        return response

    def put(self, request, car_id):
        car = owned_car_or_404(request.user, car_id)
        serializer = serializers.CarWriteSerializer(car, data=normalized_car_data(request), partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(status=models.Car.Status.PENDING, moderation_reason=None)
        if hasattr(request.data, "getlist"):
            existing_values = request.data.getlist("ExistingImageIds") or request.data.getlist("existingImageIds")
            if existing_values:
                existing_ids = [int(value) for value in existing_values]
                car.images.exclude(id__in=existing_ids).delete()
            new_images = []
            start = car.images.count()
            for index, file in enumerate(request.FILES.getlist("Images") or request.FILES.getlist("images")):
                validate_image_upload(file)
                new_images.append(models.CarImage.objects.create(
                    car=car, image=file, display_order=start + index, is_main=False
                ))
            existing = {f"existing:{image.id}": image for image in car.images.all()}
            new = {f"new:{index}": image for index, image in enumerate(new_images)}
            keyed = {**existing, **new}
            order = request.data.getlist("ImageOrder") or request.data.getlist("imageOrder")
            for index, key in enumerate(order):
                if key in keyed:
                    keyed[key].display_order = index
                    keyed[key].save(update_fields=["display_order"])
            main_key = request.data.get("mainImageKey") or request.data.get("MainImageKey")
            if main_key in keyed:
                car.images.update(is_main=False)
                keyed[main_key].is_main = True
                keyed[main_key].save(update_fields=["is_main"])
        return ok(serializers.CarDetailsSerializer(car, context={"request": request}).data, "Car updated")

    def delete(self, request, car_id):
        car = owned_car_or_404(request.user, car_id)
        write_audit(request, "CarDeleted", "Car", car.id, car.title)
        car.delete()
        return ok(message="Car deleted")


class RelatedCarsView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.CarSummarySerializer

    def get(self, request, car_id):
        car = get_object_or_404(models.Car, id=car_id)
        query = car_queryset().filter(status=models.Car.Status.AVAILABLE).exclude(id=car.id).filter(
            Q(brand=car.brand) | Q(body_type=car.body_type)
        )[:6]
        return ok(serializers.CarSummarySerializer(query, many=True, context={"request": request}).data)


class SellerCarsPublicView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.CarSummarySerializer

    def get(self, request, seller_id):
        return ok(page(request, car_queryset().filter(seller_id=seller_id, status=models.Car.Status.AVAILABLE), serializers.CarSummarySerializer))


class MyCarsView(APIView):
    serializer_class = serializers.CarSummarySerializer
    def get(self, request):
        return ok(page(request, car_queryset().filter(seller=request.user), serializers.CarSummarySerializer))


class FavoritesView(APIView):
    serializer_class = serializers.CarSummarySerializer
    def get(self, request):
        return ok(page(request, car_queryset().filter(favorites__user=request.user), serializers.CarSummarySerializer))


class FavoriteActionView(APIView):
    def post(self, request, car_id):
        car = get_object_or_404(models.Car, id=car_id, status=models.Car.Status.AVAILABLE)
        models.Favorite.objects.get_or_create(user=request.user, car=car)
        return ok(message="Added to favorites")

    def delete(self, request, car_id):
        models.Favorite.objects.filter(user=request.user, car_id=car_id).delete()
        return ok(message="Removed from favorites")


class SellerReviewsView(APIView):
    serializer_class = serializers.ReviewWriteSerializer
    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == "GET" else [permissions.IsAuthenticated()]

    def get(self, request, seller_id):
        query = models.Review.objects.select_related("reviewer").filter(seller_id=seller_id, status=models.Review.Status.APPROVED)
        return ok(page(request, query, serializers.ReviewSerializer))

    def post(self, request, seller_id):
        if request.user.id == seller_id:
            return fail("You cannot review yourself.")
        seller = get_object_or_404(models.User, id=seller_id, is_deleted=False)
        serializer = serializers.ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(reviewer=request.user, seller=seller)
        return ok(serializers.ReviewSerializer(review, context={"request": request}).data, "Review submitted", status=201)


class MyReviewsView(APIView):
    serializer_class = serializers.ReviewSerializer
    def get(self, request):
        query = models.Review.objects.select_related("reviewer").filter(reviewer=request.user)
        seller_id = request.query_params.get("sellerId")
        if seller_id:
            review = query.filter(seller_id=seller_id).first()
            return ok(serializers.ReviewSerializer(review, context={"request": request}).data if review else None)
        return ok(page(request, query, serializers.ReviewSerializer))


class ReviewDetailView(APIView):
    serializer_class = serializers.ReviewWriteSerializer
    def put(self, request, review_id):
        review = get_object_or_404(models.Review, id=review_id, reviewer=request.user)
        serializer = serializers.ReviewWriteSerializer(review, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(status=models.Review.Status.PENDING)
        return ok(serializers.ReviewSerializer(review, context={"request": request}).data)

    def delete(self, request, review_id):
        get_object_or_404(models.Review, id=review_id, reviewer=request.user).delete()
        return ok(message="Review deleted")


class ChatsView(APIView):
    serializer_class = serializers.ChatSerializer
    def get(self, request):
        latest_message = models.Message.objects.filter(chat_id=OuterRef("pk")).order_by("-sent_at", "-id")
        query = models.Chat.objects.select_related(
            "car", "buyer", "seller", "buyer__realtime_presence", "seller__realtime_presence"
        ).filter(
            Q(buyer=request.user) | Q(seller=request.user)
        ).annotate(
            last_message_content=Subquery(latest_message.values("content")[:1]),
            last_message_at=Subquery(latest_message.values("sent_at")[:1], output_field=DateTimeField()),
            unread_count=Count(
                "messages",
                filter=Q(messages__is_read=False) & ~Q(messages__sender=request.user),
            ),
        ).order_by("-updated_at")
        return ok(page(request, query, serializers.ChatSerializer))


class CreateChatView(APIView):
    serializer_class = serializers.CreateChatRequestSerializer
    @transaction.atomic
    def post(self, request, car_id):
        car = get_object_or_404(models.Car.objects.select_related("seller"), id=car_id, status=models.Car.Status.AVAILABLE)
        if car.seller_id == request.user.id:
            return fail("You cannot chat about your own listing.")
        blocked = models.UserBlock.objects.filter(
            Q(blocker=request.user, blocked_user=car.seller) | Q(blocker=car.seller, blocked_user=request.user)
        ).exists()
        if blocked or not car.seller.enable_messages:
            return fail("Messaging is unavailable.", status=403)
        chat, _ = models.Chat.objects.get_or_create(car=car, buyer=request.user, defaults={"seller": car.seller})
        content = request.data.get("message", "").strip()
        if not content:
            return fail("message is required.")
        models.Message.objects.create(chat=chat, sender=request.user, content=content)
        return ok(serializers.ChatSerializer(chat, context={"request": request}).data, "Chat opened", status=201)


class ChatMessagesView(APIView):
    serializer_class = serializers.SendMessageRequestSerializer
    def get(self, request, chat_id):
        chat = participant_or_404(request.user, chat_id)
        return ok(page(request, chat.messages.select_related("sender"), serializers.MessageSerializer))

    def post(self, request, chat_id):
        chat = participant_or_404(request.user, chat_id)
        other = chat.seller if request.user.id == chat.buyer_id else chat.buyer
        if models.UserBlock.objects.filter(Q(blocker=request.user, blocked_user=other) | Q(blocker=other, blocked_user=request.user)).exists():
            return fail("Messaging is unavailable.", status=403)
        content = request.data.get("content", "").strip()
        if not content or len(content) > 2000:
            return fail("content is required and must not exceed 2000 characters.")
        message = models.Message.objects.create(chat=chat, sender=request.user, content=content)
        chat.save(update_fields=["updated_at"])
        return ok(serializers.MessageSerializer(message).data, "Message sent", status=201)


class ChatReadView(APIView):
    def patch(self, request, chat_id):
        chat = participant_or_404(request.user, chat_id)
        count = chat.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
        enqueue_event(f"chat_{chat.id}", "messages.read", {
            "chatId": chat.id, "readerId": request.user.id, "markedReadCount": count,
        })
        return ok({"markedReadCount": count})


class VehicleHistoryListView(APIView):
    serializer_class = serializers.VehicleHistorySerializer
    def get_permissions(self):
        return [permissions.AllowAny()] if self.request.method == "GET" else [permissions.IsAuthenticated()]

    def get(self, request, car_id):
        return ok(serializers.VehicleHistorySerializer(
            models.VehicleHistory.objects.filter(car_id=car_id), many=True, context={"request": request}
        ).data)

    def post(self, request, car_id):
        car = owned_car_or_404(request.user, car_id)
        serializer = serializers.VehicleHistorySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(car=car)
        return ok(serializer.data, "History created", status=201)


class VehicleHistoryDetailView(APIView):
    serializer_class = serializers.VehicleHistorySerializer
    def put(self, request, history_id):
        item = get_object_or_404(models.VehicleHistory.objects.select_related("car"), id=history_id)
        owned_car_or_404(request.user, item.car_id)
        serializer = serializers.VehicleHistorySerializer(item, data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(serializer.data)

    def delete(self, request, history_id):
        item = get_object_or_404(models.VehicleHistory.objects.select_related("car"), id=history_id)
        owned_car_or_404(request.user, item.car_id)
        item.delete()
        return ok(message="History deleted")


class ContactCreateView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.ContactMessageSerializer
    throttle_scope = "contact"

    def post(self, request, car_id):
        car = get_object_or_404(models.Car, id=car_id, status=models.Car.Status.AVAILABLE)
        serializer = serializers.ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(car=car, seller=car.seller)
        return ok(serializer.data, "Message sent", status=201)


class ContactInboxView(APIView):
    serializer_class = serializers.ContactMessageSerializer
    def get(self, request):
        query = models.ContactMessage.objects.filter(seller=request.user).order_by("-created_at")
        if request.query_params.get("isRead") in ("true", "false"):
            query = query.filter(is_read=request.query_params["isRead"] == "true")
        return ok(page(request, query, serializers.ContactMessageSerializer))


class ContactDetailView(APIView):
    serializer_class = serializers.ContactMessageSerializer
    def get_object(self, request, contact_id):
        return get_object_or_404(models.ContactMessage, id=contact_id, seller=request.user)

    def get(self, request, contact_id):
        return ok(serializers.ContactMessageSerializer(self.get_object(request, contact_id)).data)

    def patch(self, request, contact_id):
        item = self.get_object(request, contact_id)
        item.is_read = True
        item.save(update_fields=["is_read"])
        return ok(serializers.ContactMessageSerializer(item).data)

    def delete(self, request, contact_id):
        self.get_object(request, contact_id).delete()
        return ok(message="Message deleted")


class SettingsView(APIView):
    serializer_class = serializers.SettingsSerializer
    def get(self, request):
        return ok(serializers.SettingsSerializer(request.user).data)

    def put(self, request):
        serializer = serializers.SettingsSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(serializer.data, "Settings updated")


class CloseAccountView(APIView):
    serializer_class = serializers.CloseAccountRequestSerializer
    def delete(self, request):
        allowed = {"NoLongerNeeded", "PrivacyConcerns", "TooManyNotifications", "BadExperience", "Other"}
        reason = request.data.get("reason")
        details = request.data.get("details")
        if reason not in allowed or (reason == "Other" and not details):
            return fail("A valid reason is required; details are required for Other.")
        user = request.user
        user.is_deleted = True
        user.is_active = False
        user.deleted_at = timezone.now()
        user.deletion_reason = reason
        user.deletion_details = details
        user.save()
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)
        write_audit(request, "AccountClosed", "User", user.id, reason)
        response = ok(message="Account closed")
        response.delete_cookie("refreshToken")
        return response


class NotificationsView(APIView):
    serializer_class = serializers.NotificationSerializer
    def get(self, request):
        query = models.Notification.objects.filter(user=request.user).order_by("-created_at")
        if request.query_params.get("isRead") in ("true", "false"):
            query = query.filter(is_read=request.query_params["isRead"] == "true")
        if request.query_params.get("type"):
            query = query.filter(type=request.query_params["type"])
        return ok(page(request, query, serializers.NotificationSerializer))


class NotificationPreferencesView(APIView):
    EVENT_TYPES = ("ChatMessage", "ContactInquiry", "ListingApproved", "ListingRejected",
                   "ListingPendingReview", "ReportResolved", "ReportDismissed")

    def get(self, request):
        for event_type in self.EVENT_TYPES:
            models.NotificationPreference.objects.get_or_create(user=request.user, event_type=event_type)
        items = models.NotificationPreference.objects.filter(user=request.user).order_by("event_type")
        return ok(serializers.NotificationPreferenceSerializer(items, many=True).data)

    def put(self, request):
        serializer = serializers.NotificationPreferencesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data["preferences"]:
            models.NotificationPreference.objects.update_or_create(
                user=request.user,
                event_type=item["event_type"],
                defaults={"is_enabled": item["is_enabled"]},
            )
        items = models.NotificationPreference.objects.filter(user=request.user).order_by("event_type")
        return ok(serializers.NotificationPreferenceSerializer(items, many=True).data)


class NotificationUnreadView(APIView):
    def get(self, request):
        return ok({"count": models.Notification.objects.filter(user=request.user, is_read=False).count()})


class NotificationActionView(APIView):
    def patch(self, request, notification_id):
        item = get_object_or_404(models.Notification, id=notification_id, user=request.user)
        item.is_read = True
        item.read_at = timezone.now()
        item.save(update_fields=["is_read", "read_at"])
        return ok(serializers.NotificationSerializer(item).data)

    def delete(self, request, notification_id):
        get_object_or_404(models.Notification, id=notification_id, user=request.user).delete()
        return ok(message="Notification deleted")


class NotificationReadAllView(APIView):
    def patch(self, request):
        count = models.Notification.objects.filter(user=request.user, is_read=False).update(is_read=True, read_at=timezone.now())
        return ok({"count": 0, "markedReadCount": count})


class SavedSearchListView(APIView):
    serializer_class = serializers.SavedSearchSerializer
    def get(self, request):
        return ok(serializers.SavedSearchSerializer(models.SavedSearch.objects.filter(user=request.user), many=True).data)

    def post(self, request):
        serializer = serializers.SavedSearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return ok(serializer.data, "Search saved", status=201)


class SavedSearchDetailView(APIView):
    serializer_class = serializers.SavedSearchSerializer
    def put(self, request, search_id):
        item = get_object_or_404(models.SavedSearch, id=search_id, user=request.user)
        serializer = serializers.SavedSearchSerializer(item, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return ok(serializer.data)

    def delete(self, request, search_id):
        get_object_or_404(models.SavedSearch, id=search_id, user=request.user).delete()
        return ok(message="Saved search deleted")


class BlockedUsersView(APIView):
    serializer_class = serializers.PublicUserSerializer
    def get(self, request):
        query = models.User.objects.filter(blocks_received__blocker=request.user)
        return ok(page(request, query, serializers.PublicUserSerializer))


class BlockUserView(APIView):
    def post(self, request, user_id):
        if request.user.id == user_id:
            return fail("You cannot block yourself.")
        target = get_object_or_404(models.User, id=user_id, is_deleted=False)
        models.UserBlock.objects.get_or_create(blocker=request.user, blocked_user=target)
        return ok(message="User blocked")

    def delete(self, request, user_id):
        models.UserBlock.objects.filter(blocker=request.user, blocked_user_id=user_id).delete()
        return ok(message="User unblocked")


class ReportsView(APIView):
    serializer_class = serializers.ReportSerializer
    def get(self, request):
        return ok(page(request, models.Report.objects.filter(reporter=request.user).order_by("-created_at"), serializers.ReportSerializer))

    def post(self, request):
        serializer = serializers.ReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_type = serializer.validated_data["target_type"]
        target_id = serializer.validated_data["target_id"]
        if target_type == "User" and target_id == request.user.id:
            return fail("You cannot report yourself.")
        if models.Report.objects.filter(reporter=request.user, target_type=target_type, target_id=target_id, status="Open").exists():
            return fail("You already have an open report for this target.")
        serializer.save(reporter=request.user)
        return ok(serializer.data, "Report submitted", status=201)


class SellerDashboardView(APIView):
    def get(self, request):
        cars = models.Car.objects.filter(seller=request.user)
        aggregate = cars.aggregate(
            totalListings=Count("id", distinct=True),
            activeListings=Count("id", filter=Q(status=models.Car.Status.AVAILABLE), distinct=True),
            soldListings=Count("id", filter=Q(status=models.Car.Status.SOLD), distinct=True),
            reservedListings=Count("id", filter=Q(status=models.Car.Status.RESERVED), distinct=True),
            inactiveListings=Count("id", filter=Q(status=models.Car.Status.INACTIVE), distinct=True),
            totalViews=Sum("views"),
        )
        favorites_received = models.Favorite.objects.filter(car__seller=request.user).count()
        average = models.Review.objects.filter(seller=request.user, status=models.Review.Status.APPROVED).aggregate(value=Avg("rating"))["value"]
        image_counts = models.CarImage.objects.filter(car__seller=request.user).aggregate(
            pending=Count("id", filter=Q(processing_status__in=("Pending", "Processing"))),
            failed=Count("id", filter=Q(processing_status="Failed")),
        )
        data = {
            "totalListings": aggregate["totalListings"],
            "activeListings": aggregate["activeListings"],
            "soldListings": aggregate["soldListings"],
            "reservedListings": aggregate["reservedListings"],
            "inactiveListings": aggregate["inactiveListings"],
            "totalViews": aggregate["totalViews"] or 0,
            "favoritesReceived": favorites_received,
            "averageRating": round(average or 0, 2),
            "pendingImageCount": image_counts["pending"],
            "failedImageCount": image_counts["failed"],
        }
        return ok(data)


class SellerCarDetailView(APIView):
    def get(self, request, car_id):
        car = owned_car_or_404(request.user, car_id)
        data = dict(serializers.CarDetailsSerializer(car, context={"request": request}).data)
        data.update({
            "carBrandId": car.brand_id, "carModelId": car.model_id, "bodyTypeId": car.body_type_id,
            "carConditionId": car.condition_id, "transmissionId": car.transmission_id,
            "fuelTypeId": car.fuel_type_id, "featureIds": list(car.features.values_list("id", flat=True)),
            "moderationReason": car.moderation_reason, "favoritesCount": car.favorites.count(),
            "imageProcessing": serializers.SellerCarImageSerializer(car.images.all(), many=True, context={"request": request}).data,
        })
        return ok(data)


class SellerCarImagesView(APIView):
    serializer_class = serializers.SellerCarImageSerializer

    def get(self, request, car_id):
        car = owned_car_or_404(request.user, car_id)
        return ok(serializers.SellerCarImageSerializer(car.images.all(), many=True, context={"request": request}).data)


class SellerCarImageRetryView(APIView):
    def post(self, request, car_id, image_id):
        car = owned_car_or_404(request.user, car_id)
        image = get_object_or_404(car.images, id=image_id)
        image.processing_status = "Pending"
        image.processing_error = None
        image.save(update_fields=["processing_status", "processing_error"])
        from .tasks import process_car_image
        transaction.on_commit(lambda: process_car_image.delay(image.id))
        return ok(message="Image processing queued.")


class CarUploadView(APIView):
    parser_classes = [MultiPartParser]
    serializer_class = serializers.ProfileImageRequestSerializer
    throttle_scope = "uploads"

    def post(self, request):
        file = request.FILES.get("File") or request.FILES.get("file")
        if not file:
            return fail("File is required.")
        validate_image_upload(file)
        image = models.CarImage(image=file)
        image.image.save(file.name, file, save=False)
        return ok(request.build_absolute_uri(image.image.url), "File uploaded")


class SellerCarStatusView(APIView):
    serializer_class = serializers.SellerStatusRequestSerializer
    def patch(self, request, car_id):
        car = owned_car_or_404(request.user, car_id)
        allowed = {models.Car.Status.SOLD, models.Car.Status.RESERVED, models.Car.Status.INACTIVE, models.Car.Status.AVAILABLE}
        new_status = request.data.get("status")
        if new_status not in allowed:
            return fail("Invalid status.")
        if new_status == models.Car.Status.AVAILABLE and car.status not in (models.Car.Status.RESERVED, models.Car.Status.INACTIVE):
            return fail("Only a reserved or inactive listing can be made available.")
        car.status = new_status
        car.save(update_fields=["status"])
        write_audit(request, "CarStatusChanged", "Car", car.id, new_status)
        return ok(serializers.CarSummarySerializer(car, context={"request": request}).data)


class ListingDraftView(APIView):
    serializer_class = serializers.ListingDraftRequestSerializer
    def get(self, request):
        draft = models.CarListingDraft.objects.filter(user=request.user).first()
        return ok({"payload": draft.payload, "step": draft.step, "updatedAt": draft.updated_at} if draft else None)

    def put(self, request):
        payload = request.data.get("payload", request.data)
        step = request.data.get("step", 1)
        draft, _ = models.CarListingDraft.objects.update_or_create(
            user=request.user, defaults={"payload": payload, "step": step}
        )
        return ok({"payload": draft.payload, "step": draft.step, "updatedAt": draft.updated_at}, "Draft saved")

    def delete(self, request):
        models.CarListingDraft.objects.filter(user=request.user).delete()
        return ok(message="Draft deleted")


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class AdminCarsView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ModerationCarSerializer

    def get(self, request):
        query = car_queryset()
        if request.query_params.get("status"):
            query = query.filter(status=request.query_params["status"])
        return ok(page(request, query, serializers.ModerationCarSerializer))


class AdminCarDetailView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ModerateCarRequestSerializer

    def get(self, request, car_id):
        car = get_object_or_404(car_queryset(), id=car_id)
        return ok(serializers.ModerationCarSerializer(car, context={"request": request}).data)

    @transaction.atomic
    def patch(self, request, car_id):
        car = get_object_or_404(models.Car, id=car_id)
        decision = request.data.get("decision")
        decision = {1: "Approve", 2: "Reject", "1": "Approve", "2": "Reject"}.get(decision, decision)
        if decision not in ("Approve", "Reject"):
            return fail("decision must be Approve or Reject.")
        if car.status != models.Car.Status.PENDING:
            return fail("This listing has already been moderated.")
        if decision == "Reject" and not request.data.get("reason"):
            return fail("A rejection reason is required.")
        previous = car.status
        car.status = models.Car.Status.AVAILABLE if decision == "Approve" else models.Car.Status.REJECTED
        car.moderation_reason = request.data.get("reason") if decision == "Reject" else None
        car.moderated_at = timezone.now()
        car.moderated_by = request.user
        car.save()
        models.ModerationHistory.objects.create(
            car=car, admin_user=request.user, previous_status=previous, new_status=car.status, reason=car.moderation_reason
        )
        write_audit(request, f"Listing{decision}d", "Car", car.id, car.moderation_reason)
        models.Notification.objects.create(
            user=car.seller,
            type="ListingApproved" if decision == "Approve" else "ListingRejected",
            title=f"Listing {decision.lower()}d",
            message=f'Your listing "{car.title}" was {decision.lower()}d.',
            related_entity_type="Car", related_entity_id=car.id, action_url=f"/cars/{car.id}",
        )
        return ok(serializers.CarSummarySerializer(car, context={"request": request}).data, "Moderation completed")


class AdminStatisticsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return ok(models.Car.objects.aggregate(
            pending=Count("id", filter=Q(status=models.Car.Status.PENDING)),
            approved=Count("id", filter=Q(status=models.Car.Status.AVAILABLE)),
            rejected=Count("id", filter=Q(status=models.Car.Status.REJECTED)),
        ))


class AdminReportsView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ReportSerializer

    def get(self, request):
        query = models.Report.objects.all().order_by("-created_at")
        if request.query_params.get("status"):
            query = query.filter(status=request.query_params["status"])
        if request.query_params.get("targetType"):
            query = query.filter(target_type=request.query_params["targetType"])
        return ok(page(request, query, serializers.ReportSerializer))


class AdminReportActionView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ModerateReportRequestSerializer

    def patch(self, request, report_id):
        item = get_object_or_404(models.Report, id=report_id, status="Open")
        decision = request.data.get("decision")
        if decision not in ("Resolve", "Dismiss"):
            return fail("decision must be Resolve or Dismiss.")
        item.status = "Resolved" if decision == "Resolve" else "Dismissed"
        item.resolved_at = timezone.now()
        item.resolved_by = request.user
        item.resolution_note = request.data.get("note")
        item.save()
        write_audit(request, f"Report{decision}d", "Report", item.id, item.resolution_note)
        models.Notification.objects.create(
            user=item.reporter, type=f"Report{item.status}", title=f"Report {item.status.lower()}",
            message="An administrator reviewed your report.", related_entity_type="Report", related_entity_id=item.id,
        )
        return ok(serializers.ReportSerializer(item).data)


class AdminReviewsView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ReviewSerializer

    def get(self, request):
        query = models.Review.objects.select_related("reviewer").all()
        if request.query_params.get("status"):
            query = query.filter(status=request.query_params["status"])
        return ok(page(request, query, serializers.ReviewSerializer))


class AdminReviewActionView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ModerateReviewRequestSerializer

    def patch(self, request, review_id):
        item = get_object_or_404(models.Review, id=review_id)
        decision = request.data.get("decision")
        item.status = models.Review.Status.APPROVED if decision in ("Approve", 1, "1") else models.Review.Status.REJECTED
        item.moderation_reason = request.data.get("reason")
        item.save()
        write_audit(request, f"Review{item.status}", "Review", item.id, item.moderation_reason)
        if item.status == models.Review.Status.APPROVED:
            stats = models.Review.objects.filter(seller=item.seller, status=models.Review.Status.APPROVED).aggregate(
                rating=Avg("rating"), count=Count("id")
            )
            models.Car.objects.filter(seller=item.seller).update(rating=stats["rating"] or 0, review_count=stats["count"])
        return ok(serializers.ReviewSerializer(item, context={"request": request}).data)


class AdminModerationHistoryView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.ModerationHistorySerializer

    def get(self, request, car_id):
        items = models.ModerationHistory.objects.select_related("admin_user").filter(car_id=car_id).order_by("-created_at")
        return ok(serializers.ModerationHistorySerializer(items, many=True).data)


class AdminAuditLogsView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.AuditLogSerializer

    def queryset(self, request):
        query = models.AuditLog.objects.select_related("actor").all().order_by("-created_at")
        if request.query_params.get("action"):
            query = query.filter(action=request.query_params["action"])
        if request.query_params.get("entityType"):
            query = query.filter(entity_type=request.query_params["entityType"])
        search = request.query_params.get("search")
        if search:
            query = query.filter(Q(details__icontains=search) | Q(entity_id__icontains=search) | Q(actor__full_name__icontains=search))
        return query

    def get(self, request):
        return ok(page(request, self.queryset(request), serializers.AuditLogSerializer))


class AdminAuditLogsExportView(AdminAuditLogsView):
    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="audit-logs.csv"'
        writer = csv.writer(response)
        writer.writerow(["Id", "Actor", "Action", "EntityType", "EntityId", "Details", "IpAddress", "CreatedAt"])
        for item in self.queryset(request)[:10000]:
            writer.writerow([item.id, item.actor.full_name if item.actor else "", item.action, item.entity_type,
                             item.entity_id or "", item.details or "", item.ip_address or "", item.created_at.isoformat()])
        return response


class AdminDeadLettersView(APIView):
    permission_classes = [IsAdmin]
    serializer_class = serializers.DeadLetterEventSerializer

    def get(self, request):
        query = models.RealtimeOutboxEvent.objects.filter(dead_lettered_at__isnull=False).order_by("-dead_lettered_at")
        return ok(page(request, query, serializers.DeadLetterEventSerializer))


class AdminDeadLetterRetryView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, event_id):
        event = get_object_or_404(models.RealtimeOutboxEvent, public_id=event_id)
        event.attempts = 0
        event.dead_lettered_at = None
        event.last_error = None
        event.save(update_fields=["attempts", "dead_lettered_at", "last_error"])
        from .realtime.publisher import dispatch_event
        transaction.on_commit(lambda: dispatch_event(event.id))
        return ok(message="Event queued for retry")
