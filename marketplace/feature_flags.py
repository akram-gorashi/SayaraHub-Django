import hashlib
from functools import wraps

from django.core.cache import cache

from . import models
from .responses import fail


def is_feature_enabled(key, user=None, default=False):
    cached = cache.get(f"feature-flag:{key}")
    if cached is None:
        flag = models.FeatureFlag.objects.filter(key=key).values(
            "is_enabled", "rollout_percentage"
        ).first()
        cached = (flag["is_enabled"], flag["rollout_percentage"]) if flag else (default, 100)
        cache.set(f"feature-flag:{key}", cached, timeout=60)

    enabled, percentage = cached
    if not enabled or percentage <= 0:
        return False
    if percentage >= 100:
        return True
    identity = str(user.pk) if user and user.is_authenticated else "anonymous"
    bucket = int(hashlib.sha256(f"{key}:{identity}".encode()).hexdigest()[:8], 16) % 100
    return bucket < percentage


def feature_required(key):
    def decorator(view_method):
        @wraps(view_method)
        def wrapped(self, request, *args, **kwargs):
            if not is_feature_enabled(key, request.user):
                return fail("This feature is not currently available.", status=404)
            return view_method(self, request, *args, **kwargs)
        return wrapped
    return decorator
