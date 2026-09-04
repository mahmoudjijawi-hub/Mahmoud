"""قفل دخول لوحة الإدارة وواجهة الـ API بعد خمس محاولات فاشلة — عبر الـ cache."""
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

API_LOGIN_PATHS = {
    "/api/token/",
    "/api/login/",
    "/api/auth/login/",
    "/api/auth/token/",
}


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


def _safe_cache_part(value):
    text = str(value or "unknown")
    ascii_ok = re.sub(r"[^A-Za-z0-9._-]", "_", text)[:80]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{ascii_ok}:{digest}"


def cache_keys(request):
    """مفتاح لكل IP حتى لا يصفر العداد بتغيير اسم المستخدم، مع تخزين IP/اسم المستخدم."""
    ident = client_ip(request) or "unknown"
    payload = login_payload(request)
    username = str(
        payload.get("username")
        or payload.get("userName")
        or payload.get("name")
        or ""
    ).strip().lower()[:80]
    ip_key = _safe_cache_part(ident)
    user_key = _safe_cache_part(username or "-")
    return {
        "fails": f"login_lock:fails:{ip_key}",
        "lock": f"login_lock:lock:{ip_key}",
        "combo": f"login_lock:combo:{ip_key}:{user_key}",
    }


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


def is_api_login_path(request):
    return _normalize_path(request.path) in API_LOGIN_PATHS


def is_special_number_only(request):
    payload = login_payload(request)
    special = str(
        payload.get("special_number")
        or payload.get("specialNumber")
        or payload.get("special")
        or ""
    ).strip()
    username = str(
        payload.get("username")
        or payload.get("userName")
        or payload.get("name")
        or ""
    ).strip()
    password = str(payload.get("password") or payload.get("Password") or "").strip()
    return bool(special) and not username and not password


def current_state(request):
    keys = cache_keys(request)
    now = time.time()
    lock_until = cache.get(keys["lock"])
    if lock_until:
        try:
            lock_until = float(lock_until)
        except (TypeError, ValueError):
            lock_until = 0
        if lock_until > now:
            wait = max(int(lock_until - now), 1)
            return True, wait, 0
        cache.delete(keys["fails"])
        cache.delete(keys["lock"])
        cache.delete(keys["combo"])

    fails = int(cache.get(keys["fails"]) or 0)
    if fails >= LIMIT:
        cache.delete(keys["fails"])
        cache.delete(keys["combo"])
        fails = 0
    remaining = max(LIMIT - fails, 0)
    return False, 0, remaining


def register_failure(request):
    keys = cache_keys(request)
    blocked, wait, remaining = current_state(request)
    if blocked:
        return True, wait, 0
    fails = int(cache.get(keys["fails"]) or 0) + 1
    cache.set(keys["fails"], fails, timeout=FAIL_TTL)
    cache.set(keys["combo"], fails, timeout=FAIL_TTL)
    if fails >= LIMIT:
        lock_until = time.time() + LOCKOUT_SECONDS
        cache.set(keys["lock"], lock_until, timeout=LOCKOUT_SECONDS)
        return True, LOCKOUT_SECONDS, 0
    return False, 0, max(LIMIT - fails, 0)


def register_success(request):
    keys = cache_keys(request)
    cache.delete(keys["fails"])
    cache.delete(keys["lock"])
    cache.delete(keys["combo"])
    return 0, LIMIT


def rate_limit_headers(remaining, wait=0):
    return {
        "X-RateLimit-Limit": str(LIMIT),
        "X-RateLimit-Remaining": str(max(int(remaining), 0)),
        "X-RateLimit-Reset": str(max(int(wait or 0), 0)),
    }


def lock_json_payload(wait):
    wait = max(int(wait or LOCKOUT_SECONDS), 1)
    return {
        "error": LOCK_MESSAGE,
        "detail": LOCK_MESSAGE,
        "message": LOCK_MESSAGE,
        "non_field_errors": [LOCK_MESSAGE],
        "success": False,
        "code": "too_many_requests",
        "wait": wait,
        "retry_after": wait,
        "locked": True,
    }
