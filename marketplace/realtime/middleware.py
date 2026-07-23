from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from rest_framework_simplejwt.authentication import JWTAuthentication


@database_sync_to_async
def user_for_token(raw_token):
    try:
        authentication = JWTAuthentication()
        validated = authentication.get_validated_token(raw_token)
        return authentication.get_user(validated)
    except Exception:
        return AnonymousUser()


@database_sync_to_async
def user_for_ticket(ticket):
    if not ticket:
        return AnonymousUser()
    key = f"ws-ticket:{ticket}"
    user_id = cache.get(key)
    if not user_id:
        return AnonymousUser()
    cache.delete(key)
    return get_user_model().objects.filter(id=user_id, is_active=True).first() or AnonymousUser()


class JwtAuthMiddleware:
    """Authenticate browser WebSockets using ?token=<access JWT>."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = query.get("ticket", [""])[0]
        scope["user"] = await user_for_ticket(ticket)
        if not scope["user"].is_authenticated and settings.DEBUG:
            token = query.get("token", [""])[0]
            scope["user"] = await user_for_token(token)
        return await self.app(scope, receive, send)
