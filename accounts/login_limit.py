"""عدّاد دخول المدير في قاعدة البيانات حتى يعمل على Render بعدة عمال."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import ManagerLoginGuard

LIMIT = 5
WINDOW_SECONDS = 60
LOCKOUT_SECONDS = 120
LOCK_MESSAGE = "لقد قمت بعدة محاولات كثيرة، يرجى المحاولة مرة أخرى بعد دقيقتين."


def client_ip(request):
    forwarded = (
        request.META.get("HTTP_X_FORWARDED_FOR")
        or request.META.get("HTTP_X_REAL_IP")
        or request.META.get("HTTP_CF_CONNECTING_IP")
        or ""
    )
    if forwarded:
        return forwarded.split(",")[0].strip()[:190]
    return (request.META.get("REMOTE_ADDR") or "unknown")[:190]


def lock_payload(wait):
    wait = max(int(wait or LOCKOUT_SECONDS), 1)
    return {
        "success": False,
        "detail": LOCK_MESSAGE,
        "error": LOCK_MESSAGE,
        "message": LOCK_MESSAGE,
        "non_field_errors": [LOCK_MESSAGE],
        "code": "too_many_requests",
        "wait": wait,
    }


def register_manager_password_attempt(request):
    """يسجّل محاولة حسب الـ IP. المحاولة السادسة تقفل دقيقتين."""
    ident = client_ip(request) or "unknown"
    last_error = None
    for _ in range(3):
        try:
            return _register(ident)
        except IntegrityError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return _register(ident)


def _register(ident):
    now = timezone.now()
    now_ts = now.timestamp()
    cutoff_ts = now_ts - WINDOW_SECONDS
    with transaction.atomic():
        guard, _created = ManagerLoginGuard.objects.select_for_update().get_or_create(
            ident=ident,
            defaults={"attempts": [], "locked_until": None},
        )
        if guard.locked_until and guard.locked_until > now:
            wait = int((guard.locked_until - now).total_seconds())
            return True, max(wait, 1), _info(0, guard.locked_until.timestamp())

        stamps = []
        for stamp in guard.attempts or []:
            value = _stamp_ts(stamp)
            if value is not None and value > cutoff_ts:
                stamps.append(value)
        stamps.append(now_ts)
        if len(stamps) > LIMIT:
            locked_until = now + timedelta(seconds=LOCKOUT_SECONDS)
            guard.attempts = stamps
            guard.locked_until = locked_until
            guard.save(update_fields=["attempts", "locked_until"])
            return True, LOCKOUT_SECONDS, _info(0, locked_until.timestamp())

        guard.attempts = stamps
        guard.locked_until = None
        guard.save(update_fields=["attempts", "locked_until"])
        remaining = LIMIT - len(stamps)
        return False, 0, _info(remaining, stamps[0] + WINDOW_SECONDS)


def _info(remaining, reset_ts):
    return {
        "limit": LIMIT,
        "remaining": max(0, int(remaining)),
        "reset": int(reset_ts),
    }


def _stamp_ts(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        parsed = parse_datetime(str(value))
        if parsed is None:
            return None
        return parsed.timestamp()
