"""قفل دخول لوحة Django Admin بعد خمس محاولات فاشلة — عبر الـ cache."""
import time

from django.conf import settings
from django.core.cache import cache

LIMIT = 5
LOCKOUT_SECONDS = 120
FAIL_TTL = 60 * 60 * 24
LOCK_MESSAGE = "تم تجاوز عدد المحاولات المسموح بها (5 محاولات). تم حظر المحاولة لمدة دقيقتين."


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


def cache_keys(request):
    """مفتاح واحد لكل IP حتى لا يصفر العداد بتغيير اسم المستخدم."""
    ident = client_ip(request) or "unknown"
    username = str(request.POST.get("username") or "").strip().lower()[:80]
    # نجمع IP مع اسم المستخدم للتتبع، والقفل يُحسب على الـ IP حتى تتراكم الأسماء الخاطئة
    ip_key = ident
    return {
        "fails": f"admin_login:fails:{ip_key}",
        "lock": f"admin_login:lock:{ip_key}",
        "combo": f"admin_login:combo:{ip_key}:{username or '-'}",
    }


def is_admin_login_path(request):
    """مسار دخول لوحة الإدارة الفعلي (ADMIN_URL/login/) بما فيه /admin/login/."""
    admin_prefix = "/" + str(getattr(settings, "ADMIN_URL", "admin/")).lstrip("/")
    login_path = admin_prefix.rstrip("/") + "/login/"
    path = request.path if request.path.endswith("/") else request.path + "/"
    if path == login_path:
        return True
    return path.rstrip("/") == "/admin/login"


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
