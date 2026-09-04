"""قفل دخول المدير (اسم مستخدم + كلمة مرور) بعد خمس محاولات فاشلة.

العداد يُحفظ في DatabaseCache، وإن فشل الجدول يُستخدم جدول ManagerLoginGuard
حتى يبقى القفل مشتركاً بين عمال Render.
"""
import hashlib
import json
import logging
import re
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

LIMIT = 5
LOCKOUT_SECONDS = 120
FAIL_TTL = 60 * 60 * 24
LOCK_MESSAGE = "تم تجاوز عدد المحاولات المسموح بها (5 محاولات). تم حظر المحاولة لمدة دقيقتين."
CACHE_TABLE = "django_cache"

logger = logging.getLogger("core.admin_login_limit")

API_ADMIN_LOGIN_PATHS = {
    "/api/token/",
    "/api/login/",
    "/api/admin/login/",
    "/api/auth/login/",
    "/api/auth/token/",
}

STUDENT_TEACHER_LOGIN_PATHS = {
    "/api/student-login/",
    "/api/student_login/",
}

_cache_table_ready = False
_prefer_db = False


def ensure_cache_table():
    """ينشئ جدول django_cache إن لم يوجد — ضروري على Render بعدة عمال."""
    global _cache_table_ready
    if _cache_table_ready:
        return True
    try:
        from django.core.management import call_command

        call_command("createcachetable", verbosity=0)
        _cache_table_ready = True
        return True
    except Exception:
        logger.exception("createcachetable command failed")
    try:
        tables = set(connection.introspection.table_names())
        if CACHE_TABLE in tables:
            _cache_table_ready = True
            return True
        qn = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE %s (%s varchar(255) NOT NULL PRIMARY KEY, "
                "%s text NOT NULL, %s timestamp NOT NULL)"
                % (qn(CACHE_TABLE), qn("cache_key"), qn("value"), qn("expires"))
            )
            cursor.execute(
                "CREATE INDEX %s ON %s (%s)"
                % (qn("django_cache_expires"), qn(CACHE_TABLE), qn("expires"))
            )
        _cache_table_ready = True
        return True
    except Exception:
        logger.exception("manual django_cache CREATE TABLE failed")
        return False


def client_ip(request):
    forwarded = (
        request.META.get("HTTP_X_FORWARDED_FOR")
        or request.META.get("HTTP_X_REAL_IP")
        or request.META.get("HTTP_CF_CONNECTING_IP")
        or ""
    )
    if forwarded:
        return forwarded.split(",")[0].strip()[:180]
    return (request.META.get("REMOTE_ADDR") or "unknown")[:180]


def login_payload(request):
    data = {}
    try:
        parsed = getattr(request, "data", None)
        if parsed is not None and hasattr(parsed, "get"):
            data = parsed
    except Exception:
        data = {}
    if not data:
        post = getattr(request, "POST", None)
        if post:
            data = post
    if not data:
        try:
            raw = getattr(request, "body", b"") or b""
            if raw:
                loaded = json.loads(raw.decode("utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}
    return data if hasattr(data, "get") else {}


def _field(payload, *names):
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def login_username(request):
    payload = login_payload(request)
    return _field(
        payload,
        "username",
        "userName",
        "UserName",
        "user_name",
        "login",
        "name",
        "email",
    ).lower()[:80]


def _safe_cache_part(value):
    text = str(value or "unknown")
    ascii_ok = re.sub(r"[^A-Za-z0-9._-]", "_", text)[:80]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{ascii_ok}:{digest}"


def cache_keys(request):
    """مفاتيح منفصلة لعنوان IP ولاسم المستخدم حتى يُحتسب أي منهما."""
    ip_key = _safe_cache_part(client_ip(request) or "unknown")
    username = login_username(request)
    user_key = _safe_cache_part(username or "-")
    keys = {
        "fails": f"admin_login:fails:ip:{ip_key}",
        "lock": f"admin_login:lock:ip:{ip_key}",
        "combo": f"admin_login:combo:{ip_key}:{user_key}",
        "user_fails": f"admin_login:fails:user:{user_key}" if username else "",
        "user_lock": f"admin_login:lock:user:{user_key}" if username else "",
    }
    return keys


def _normalize_path(path):
    if not path:
        return "/"
    return path if path.endswith("/") else path + "/"


def is_admin_login_path(request):
    """مسار دخول لوحة الإدارة الفعلي (ADMIN_URL/login/) بما فيه /admin/login/."""
    admin_prefix = "/" + str(getattr(settings, "ADMIN_URL", "admin/")).lstrip("/")
    login_path = admin_prefix.rstrip("/") + "/login/"
    path = _normalize_path(request.path)
    if path == login_path:
        return True
    return path.rstrip("/") == "/admin/login"


def is_student_or_teacher_login_path(request):
    return _normalize_path(request.path) in STUDENT_TEACHER_LOGIN_PATHS


def is_api_admin_login_path(request):
    return _normalize_path(request.path) in API_ADMIN_LOGIN_PATHS


def is_special_number_only(request):
    """دخول طالب/أستاذ بالرقم المميز وحده — خارج قفل المدير."""
    payload = login_payload(request)
    special = _field(payload, "special_number", "specialNumber", "special", "number")
    username = _field(
        payload,
        "username",
        "userName",
        "UserName",
        "user_name",
        "login",
        "name",
        "email",
    )
    password = _field(payload, "password", "Password", "pass", "passwd", "pwd")
    return bool(special) and not username and not password


def is_admin_password_login(request):
    """دخول المدير باسم المستخدم وكلمة المرور فقط. بلا استثناء لأي حساب مدير."""
    if is_student_or_teacher_login_path(request):
        return False
    if is_special_number_only(request):
        return False
    if is_admin_login_path(request):
        return True
    if is_api_admin_login_path(request) and request.method == "POST":
        payload = login_payload(request)
        username = _field(
            payload,
            "username",
            "userName",
            "UserName",
            "user_name",
            "login",
            "name",
            "email",
        )
        password = _field(payload, "password", "Password", "pass", "passwd", "pwd")
        return bool(username or password)
    return False


def _lock_wait(lock_until):
    now = time.time()
    if not lock_until:
        return 0
    try:
        lock_until = float(lock_until)
    except (TypeError, ValueError):
        return 0
    if lock_until <= now:
        return 0
    return max(int(lock_until - now), 1)


def _db_ident(key):
    text = str(key or "")
    if len(text) <= 190:
        return text
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:190]


def _ensure_guard_table():
    try:
        from accounts.login_limit import ensure_table

        ensure_table()
    except Exception:
        logger.exception("ManagerLoginGuard table ensure failed")


def _db_get(key):
    if not key:
        return None
    _ensure_guard_table()
    from accounts.models import ManagerLoginGuard

    row = ManagerLoginGuard.objects.filter(ident=_db_ident(key)).first()
    if row is None:
        return None
    data = row.attempts if isinstance(row.attempts, dict) else None
    if not data:
        return None
    exp = data.get("exp")
    if exp and float(exp) < time.time():
        return None
    return data.get("value")


def _db_set(key, value, timeout):
    if not key:
        return
    _ensure_guard_table()
    from accounts.models import ManagerLoginGuard

    payload = {"value": value, "exp": time.time() + int(timeout or FAIL_TTL)}
    locked_until = timezone.now() + timedelta(seconds=int(timeout or FAIL_TTL))
    ManagerLoginGuard.objects.update_or_create(
        ident=_db_ident(key),
        defaults={"attempts": payload, "locked_until": locked_until},
    )


def _db_delete(key):
    if not key:
        return
    _ensure_guard_table()
    from accounts.models import ManagerLoginGuard

    ManagerLoginGuard.objects.filter(ident=_db_ident(key)).delete()


def _db_incr(key, timeout=FAIL_TTL):
    if not key:
        return 0
    _ensure_guard_table()
    from accounts.models import ManagerLoginGuard

    ident = _db_ident(key)
    with transaction.atomic():
        row, created = ManagerLoginGuard.objects.select_for_update().get_or_create(
            ident=ident,
            defaults={
                "attempts": {"value": 1, "exp": time.time() + int(timeout)},
                "locked_until": timezone.now() + timedelta(seconds=int(timeout)),
            },
        )
        if created:
            return 1
        data = row.attempts if isinstance(row.attempts, dict) else {}
        exp = data.get("exp")
        current = 0
        if exp and float(exp) < time.time():
            current = 0
        else:
            try:
                current = int(data.get("value") or 0)
            except (TypeError, ValueError):
                current = 0
        value = current + 1
        row.attempts = {"value": value, "exp": time.time() + int(timeout)}
        row.locked_until = timezone.now() + timedelta(seconds=int(timeout))
        row.save(update_fields=["attempts", "locked_until"])
        return value


def _cache_get(key):
    return cache.get(key)


def _cache_set(key, value, timeout):
    cache.set(key, value, timeout=timeout)


def _cache_delete(key):
    cache.delete(key)


def _cache_incr(key, timeout=FAIL_TTL):
    try:
        value = int(cache.incr(key))
        try:
            cache.touch(key, timeout)
        except Exception:
            pass
        return value
    except ValueError:
        if cache.add(key, 1, timeout=timeout):
            return 1
        try:
            return int(cache.incr(key))
        except ValueError:
            cache.set(key, 1, timeout=timeout)
            return 1


def kv_get(key):
    if not key:
        return None
    if not _prefer_db:
        try:
            return _cache_get(key)
        except Exception as exc:
            logger.warning("cache get failed; falling back to database: %s", exc)
            ensure_cache_table()
            try:
                return _cache_get(key)
            except Exception:
                _mark_db_fallback()
    try:
        return _db_get(key)
    except Exception:
        logger.exception("db fallback get failed")
        return None


def kv_set(key, value, timeout):
    if not key:
        return
    if not _prefer_db:
        try:
            _cache_set(key, value, timeout)
            return
        except Exception as exc:
            logger.warning("cache set failed; falling back to database: %s", exc)
            ensure_cache_table()
            try:
                _cache_set(key, value, timeout)
                return
            except Exception:
                _mark_db_fallback()
    try:
        _db_set(key, value, timeout)
    except Exception:
        logger.exception("db fallback set failed")


def kv_delete(key):
    if not key:
        return
    if not _prefer_db:
        try:
            _cache_delete(key)
        except Exception:
            ensure_cache_table()
            try:
                _cache_delete(key)
            except Exception:
                _mark_db_fallback()
    try:
        _db_delete(key)
    except Exception:
        logger.exception("db fallback delete failed")


def kv_incr(key, timeout=FAIL_TTL):
    if not key:
        return 0
    if not _prefer_db:
        try:
            return _cache_incr(key, timeout)
        except Exception as exc:
            logger.warning("cache incr failed; falling back to database: %s", exc)
            ensure_cache_table()
            try:
                return _cache_incr(key, timeout)
            except Exception:
                _mark_db_fallback()
    try:
        return _db_incr(key, timeout)
    except Exception:
        logger.exception("db fallback incr failed")
        return 0


def _mark_db_fallback():
    global _prefer_db
    _prefer_db = True


def current_state(request):
    try:
        return _current_state(request)
    except Exception:
        logger.exception("current_state failed; retrying via db fallback")
        _mark_db_fallback()
        ensure_cache_table()
        try:
            return _current_state(request)
        except Exception:
            logger.exception("current_state fallback failed")
            return False, 0, LIMIT


def _current_state(request):
    keys = cache_keys(request)
    waits = []
    for lock_name in ("lock", "user_lock"):
        lock_key = keys.get(lock_name)
        if not lock_key:
            continue
        wait = _lock_wait(kv_get(lock_key))
        if wait:
            waits.append(wait)
        else:
            expired = kv_get(lock_key)
            if expired is not None:
                kv_delete(lock_key)
    if waits:
        return True, max(waits), 0

    fails_ip = int(kv_get(keys["fails"]) or 0)
    fails_user = int(kv_get(keys["user_fails"]) or 0) if keys.get("user_fails") else 0
    if fails_ip >= LIMIT:
        kv_delete(keys["fails"])
        fails_ip = 0
    if keys.get("user_fails") and fails_user >= LIMIT:
        kv_delete(keys["user_fails"])
        fails_user = 0
    remaining = max(LIMIT - max(fails_ip, fails_user), 0)
    return False, 0, remaining


def register_failure(request):
    try:
        return _register_failure(request)
    except Exception:
        logger.exception("register_failure failed; retrying via db fallback")
        _mark_db_fallback()
        ensure_cache_table()
        try:
            return _register_failure(request)
        except Exception:
            logger.exception("register_failure fallback failed")
            return False, 0, LIMIT


def _register_failure(request):
    keys = cache_keys(request)
    blocked, wait, remaining = _current_state(request)
    if blocked:
        return True, wait, 0
    fails_ip = kv_incr(keys["fails"])
    fails_user = kv_incr(keys["user_fails"]) if keys.get("user_fails") else 0
    kv_set(keys["combo"], max(fails_ip, fails_user), FAIL_TTL)
    if fails_ip >= LIMIT or fails_user >= LIMIT:
        lock_until = time.time() + LOCKOUT_SECONDS
        kv_set(keys["lock"], lock_until, LOCKOUT_SECONDS)
        if keys.get("user_lock"):
            kv_set(keys["user_lock"], lock_until, LOCKOUT_SECONDS)
        return True, LOCKOUT_SECONDS, 0
    remaining = max(LIMIT - max(fails_ip, fails_user), 0)
    return False, 0, remaining


def register_success(request):
    try:
        keys = cache_keys(request)
        for name in ("fails", "lock", "combo", "user_fails", "user_lock"):
            key = keys.get(name)
            if key:
                kv_delete(key)
        return 0, LIMIT
    except Exception:
        logger.exception("register_success failed")
        return 0, LIMIT


def rate_limit_headers(remaining, wait=0):
    reset = LOCKOUT_SECONDS if int(remaining) <= 0 and int(wait or 0) > 0 else max(int(wait or 0), 0)
    return {
        "X-RateLimit-Limit": str(LIMIT),
        "X-RateLimit-Remaining": str(max(int(remaining), 0)),
        "X-RateLimit-Reset": str(reset),
    }


def lock_json_payload(wait=LOCKOUT_SECONDS):
    return {
        "detail": LOCK_MESSAGE,
        "error": LOCK_MESSAGE,
    }
