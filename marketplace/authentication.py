from datetime import timedelta
from typing import cast

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from . import models
from .sessions import client_ip


class SessionTrackingJWTAuthentication(JWTAuthentication):
    """Track rich session activity and immediately enforce explicit revocation."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        authenticated_user, validated_token = result
        user = cast(models.User, authenticated_user)
        session_id = validated_token.get("sid")
        if not session_id:
            return result  # Compatibility for access tokens issued before session tracking.

        session = models.AuthSession.objects.filter(id=session_id, user=user).first()
        if not session or session.revoked_at or session.expires_at <= timezone.now():
            raise AuthenticationFailed("This session has been revoked or expired.")

        now = timezone.now()
        if session.last_activity_at < now - timedelta(seconds=60):
            models.AuthSession.objects.filter(id=session.id).update(
                last_activity_at=now,
                ip_address=client_ip(request),
            )
        return user, validated_token
