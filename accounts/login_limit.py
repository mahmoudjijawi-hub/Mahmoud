"""قفل صفحة كلمة مرور المدير بعد ست محاولات — عدّاد واحد لكل المنصّة."""
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import ManagerLoginGuard

LIMIT = 5
WINDOW_SECONDS = 60
LOCKOUT_SECONDS = 120
GLOBAL_IDENT = "manager-password"
LOCK_MESSAGE = "لقد قمت بعدة محاولات كثيرة، يرجى المحاولة مرة أخرى بعد دقيقتين."

_table_ready = False


def ensure_table():
    """ينشئ جدول القفل إن نُشر الكود قبل الهجرة."""
    global _table_ready
    if _table_ready:
        return
    table = ManagerLoginGuard._meta.db_table
    if table not in connection.introspection.table_names():
        with connection.schema_editor() as editor:
            editor.create_model(ManagerLoginGuard)
    _table_ready = True


def lock_payload(wait):
    wait = max(int(wait or LOCKOUT_SECONDS), 1)
    return {
        "success": False,
        "locked": True,
        "requires_password": True,
        "role": "manager",
        "detail": LOCK_MESSAGE,
        "error": LOCK_MESSAGE,
        "message": LOCK_MESSAGE,
        "non_field_errors": [LOCK_MESSAGE],
        "code": "too_many_requests",
        "wait": wait,
    }


def current_lock():
    """هل الصفحة مقفلة الآن؟ دون زيادة العداد."""
    ensure_table()
    now = timezone.now()
    guard = ManagerLoginGuard.objects.filter(ident=GLOBAL_IDENT).first()
    if guard and guard.locked_until and guard.locked_until > now:
        wait = max(int((guard.locked_until - now).total_seconds()), 1)
        return True, wait, _info(0, guard.locked_until.timestamp())
    remaining = LIMIT
    reset_ts = now.timestamp() + WINDOW_SECONDS
    if guard:
        stamps = _fresh_stamps(guard.attempts, now.timestamp())
        remaining = max(LIMIT - len(stamps), 0)
        if stamps:
            reset_ts = stamps[0] + WINDOW_SECONDS
    return False, 0, _info(remaining, reset_ts)


def register_failure():
    """يسجّل محاولة فاشلة. المحاولة السادسة تقفل دقيقتين."""
    return _mutate("fail")


def clear_failures():
    """دخول ناجح يصفر العداد."""
    return _mutate("clear")


def _mutate(action):
    ensure_table()
    last_error = None
    for _ in range(3):
        try:
            return _mutate_once(action)
        except IntegrityError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return _mutate_once(action)


def _mutate_once(action):
    now = timezone.now()
    now_ts = now.timestamp()
    with transaction.atomic():
        guard, _created = ManagerLoginGuard.objects.select_for_update().get_or_create(
            ident=GLOBAL_IDENT,
            defaults={"attempts": [], "locked_until": None},
        )
        if action == "clear":
            guard.attempts = []
            guard.locked_until = None
            guard.save(update_fields=["attempts", "locked_until"])
            return False, 0, _info(LIMIT, now_ts + WINDOW_SECONDS)

        if guard.locked_until and guard.locked_until > now:
            wait = max(int((guard.locked_until - now).total_seconds()), 1)
            return True, wait, _info(0, guard.locked_until.timestamp())

        stamps = _fresh_stamps(guard.attempts, now_ts)
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


def _fresh_stamps(raw, now_ts):
    cutoff_ts = now_ts - WINDOW_SECONDS
    stamps = []
    for stamp in raw or []:
        value = _stamp_ts(stamp)
        if value is not None and value > cutoff_ts:
            stamps.append(value)
    return stamps


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
