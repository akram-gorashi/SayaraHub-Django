from datetime import datetime, timezone as datetime_timezone

from user_agents import parse

from . import models


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def create_auth_session(user, refresh, request=None):
    raw_user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
    parsed = parse(raw_user_agent)
    device = parsed.device.family if parsed.device.family != "Other" else (
        "Mobile device" if parsed.is_mobile else "Desktop device" if parsed.is_pc else "Unknown device"
    )
    browser = parsed.browser.family
    if parsed.browser.version_string:
        browser = f"{browser} {parsed.browser.version_string}"
    session, _ = models.AuthSession.objects.update_or_create(
        refresh_jti=refresh["jti"],
        defaults={
            "user": user,
            "device_name": device,
            "browser": browser or "Unknown browser",
            "ip_address": client_ip(request),
            "user_agent": raw_user_agent[:2000],
            "expires_at": datetime.fromtimestamp(refresh["exp"], datetime_timezone.utc),
            "revoked_at": None,
        },
    )
    return session
