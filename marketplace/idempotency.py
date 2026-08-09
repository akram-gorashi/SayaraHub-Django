import hashlib
import json
import re
from functools import wraps

from django.db import transaction
from django.http import QueryDict
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from . import models
from .responses import fail


KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def _actor_key(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    identity = f"{_client_ip(request)}|{request.META.get('HTTP_USER_AGENT', '')}"
    return f"anon:{hashlib.sha256(identity.encode()).hexdigest()[:40]}"


def _normalise(value):
    if hasattr(value, "chunks"):
        digest = hashlib.sha256()
        for chunk in value.chunks():
            digest.update(chunk)
        value.seek(0)
        return {
            "name": value.name,
            "size": value.size,
            "contentType": getattr(value, "content_type", None),
            "sha256": digest.hexdigest(),
        }
    if isinstance(value, QueryDict):
        return {key: [_normalise(item) for item in values] for key, values in sorted(value.lists())}
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _request_hash(request):
    canonical = {
        "method": request.method,
        "path": request.path,
        "data": _normalise(request.data),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def idempotent(scope):
    """Replay completed POST responses when a caller supplies Idempotency-Key."""

    def decorator(view_method):
        @wraps(view_method)
        def wrapped(self, request, *args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            if not key:
                return view_method(self, request, *args, **kwargs)
            if not KEY_PATTERN.fullmatch(key):
                return fail(
                    "Idempotency-Key must be 8-128 characters using letters, numbers, '.', '_', ':' or '-'."
                )

            fingerprint = _request_hash(request)
            with transaction.atomic():
                record, created = models.IdempotencyRecord.objects.get_or_create(
                    scope=scope,
                    actor_key=_actor_key(request),
                    key=key,
                    defaults={"request_hash": fingerprint},
                )
                if not created:
                    if record.request_hash != fingerprint:
                        return fail("This Idempotency-Key was already used for a different request.", status=409)
                    if record.completed_at and record.response_body is not None:
                        response = Response(record.response_body, status=record.response_status)
                        response["Idempotency-Replayed"] = "true"
                        return response
                    response = fail("A request with this Idempotency-Key is still processing.", status=409)
                    response["Retry-After"] = "1"
                    return response

                response = view_method(self, request, *args, **kwargs)
                if response.status_code >= 500:
                    record.delete()
                    return response
                rendered = JSONRenderer().render(response.data)
                record.response_status = response.status_code
                record.response_body = json.loads(rendered)
                record.completed_at = timezone.now()
                record.save(update_fields=["response_status", "response_body", "completed_at"])
                response["Idempotency-Replayed"] = "false"
                return response

        return wrapped

    return decorator
