"""قفل دخول المدير (اسم مستخدم + كلمة مرور) بعد خمس محاولات فاشلة — عبر DatabaseCache."""
import hashlib
import json
import re
import time

from django.conf import settings
from django.core.cache import cache

LIMIT = 5
LOCKOUT_SECONDS = 120
FAIL_TTL = 60 * 60 * 24
LOCK_MESSAGE = "تم تجاوز عدد المحاولات المسموح بها (5 محاولات). تم حظر المحاولة لمدة دقيقتين."
CACHE_TABLE = "django_cache"

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


def ensure_cache_table():
    """ينشئ جدول django_cache إن لم يوجد — ضروري على Render بعدة عمال."""
    try:
        from django.core.management import call_command

        call_command("createcachetable", verbosity=0)
    except Exception:
        pass


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


def current_state(request):
    keys = cache_keys(request)
    waits = []
    for lock_name in ("lock", "user_lock"):
        lock_key = keys.get(lock_name)
        if not lock_key:
            continue
        wait = _lock_wait(cache.get(lock_key))
        if wait:
            waits.append(wait)
        else:
            expired = cache.get(lock_key)
            if expired is not None:
                cache.delete(lock_key)
    if waits:
        return True, max(waits), 0

    fails_ip = int(cache.get(keys["fails"]) or 0)
    fails_user = int(cache.get(keys["user_fails"]) or 0) if keys.get("user_fails") else 0
    if fails_ip >= LIMIT:
        cache.delete(keys["fails"])
        fails_ip = 0
    if keys.get("user_fails") and fails_user >= LIMIT:
        cache.delete(keys["user_fails"])
        fails_user = 0
    remaining = max(LIMIT - max(fails_ip, fails_user), 0)
    return False, 0, remaining


def _incr_fail(key):
    if not key:
        return 0
    try:
        return int(cache.incr(key))
    except ValueError:
        if cache.add(key, 1, timeout=FAIL_TTL):
            return 1
        try:
            return int(cache.incr(key))
        except ValueError:
            cache.set(key, 1, timeout=FAIL_TTL)
            return 1


def register_failure(request):
    keys = cache_keys(request)
    blocked, wait, remaining = current_state(request)
    if blocked:
        return True, wait, 0
    fails_ip = _incr_fail(keys["fails"])
    try:
        cache.touch(keys["fails"], FAIL_TTL)
    except Exception:
        pass
    fails_user = _incr_fail(keys["user_fails"]) if keys.get("user_fails") else 0
    if keys.get("user_fails"):
        try:
            cache.touch(keys["user_fails"], FAIL_TTL)
        except Exception:
            pass
    cache.set(keys["combo"], max(fails_ip, fails_user), timeout=FAIL_TTL)
    if fails_ip >= LIMIT or fails_user >= LIMIT:
        lock_until = time.time() + LOCKOUT_SECONDS
        cache.set(keys["lock"], lock_until, timeout=LOCKOUT_SECONDS)
        if keys.get("user_lock"):
            cache.set(keys["user_lock"], lock_until, timeout=LOCKOUT_SECONDS)
        return True, LOCKOUT_SECONDS, 0
    remaining = max(LIMIT - max(fails_ip, fails_user), 0)
    return False, 0, remaining


def register_success(request):
    keys = cache_keys(request)
    for name in ("fails", "lock", "combo", "user_fails", "user_lock"):
        key = keys.get(name)
        if key:
            cache.delete(key)
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
