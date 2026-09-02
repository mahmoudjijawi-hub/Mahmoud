"""حدود معدّل الطلبات لمنع التخمين بالقوة الغاشمة على الدخول والرقم المميز."""
import time

from django.core.cache import cache
from rest_framework.throttling import BaseThrottle, SimpleRateThrottle, ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    """حد صارم لتسجيل دخول المدير باسم المستخدم وكلمة المرور."""

    scope = "login"


class SpecialNumberRateThrottle(SimpleRateThrottle):
    """حد صارم جداً على مسار الرقم المميز لأنه قصير وقابل للتخمين."""

    scope = "special_number"

    def allow_request(self, request, view):
        if not _is_special_number_attempt(request):
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        ident = self.get_ident(request) or "unknown"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class PaymentRateThrottle(ScopedRateThrottle):
    """حد خاص بنقاط الدفع لتقليل الإساءة."""

    scope = "payments"


class ManagerPasswordLoginThrottle(BaseThrottle):
    """
    شاشة اسم المدير وكلمة المرور:
    5 محاولات خلال دقيقة، ثم انتظار دقيقتين (429).
    """

    limit = 5
    window_seconds = 60
    lockout_seconds = 120

    def allow_request(self, request, view):
        if not _is_manager_password_attempt(request):
            return True

        ident = self.get_ident(request) or "unknown"
        now = time.time()
        history_key = f"throttle_manager_pw_hist_{ident}"
        lock_key = f"throttle_manager_pw_lock_{ident}"

        lock_until = cache.get(lock_key)
        if lock_until and float(lock_until) > now:
            remaining_wait = float(lock_until) - now
            self._attach(request, remaining=0, reset_at=float(lock_until), wait=remaining_wait)
            return False

        history = [stamp for stamp in (cache.get(history_key) or []) if now - stamp < self.window_seconds]
        if len(history) >= self.limit:
            lock_until = now + self.lockout_seconds
            cache.set(lock_key, lock_until, timeout=self.lockout_seconds)
            self._attach(request, remaining=0, reset_at=lock_until, wait=self.lockout_seconds)
            return False

        history.append(now)
        cache.set(history_key, history, timeout=self.window_seconds)
        reset_at = history[0] + self.window_seconds
        remaining = self.limit - len(history)
        self._attach(request, remaining=remaining, reset_at=reset_at, wait=None)
        return True

    def wait(self):
        return getattr(self, "wait_seconds", self.lockout_seconds)

    def _attach(self, request, remaining, reset_at, wait):
        self.wait_seconds = wait
        request._manager_login_rate_limit = {
            "limit": self.limit,
            "remaining": max(0, int(remaining)),
            "reset": int(reset_at),
        }


def _first_field(data, *keys):
    if not hasattr(data, "get"):
        return ""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value).strip()
    try:
        lowered = {str(k).lower(): v for k, v in data.items()}
    except Exception:
        return ""
    for key in keys:
        value = lowered.get(str(key).lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _is_manager_password_attempt(request):
    """فقط جسم اسم المستخدم + كلمة المرور، وليس الرقم المميز."""
    try:
        data = request.data
    except Exception:
        return False
    username = _first_field(
        data,
        "username",
        "userName",
        "UserName",
        "user_name",
        "login",
        "user",
        "User",
        "name",
        "Name",
        "email",
    )
    password = _first_field(data, "password", "Password", "pass", "passwd", "pwd")
    return bool(username or password) and not _is_special_number_attempt(request)


def _is_special_number_attempt(request):
    try:
        data = request.data
    except Exception:
        return False
    special = _first_field(data, "special_number", "specialNumber", "special", "number")
    username = _first_field(
        data,
        "username",
        "userName",
        "UserName",
        "user_name",
        "login",
        "user",
        "User",
        "name",
        "Name",
        "email",
    )
    password = _first_field(data, "password", "Password", "pass", "passwd", "pwd")
    # الرقم المميز وحده. أي اسم/كلمة مرور = صفحة المدير حتى لو بقي الرقم المميز بالجسم.
    return bool(special) and not username and not password


def apply_manager_login_rate_limit_headers(request, response):
    info = getattr(request, "_manager_login_rate_limit", None)
    if not info:
        return response
    response["X-RateLimit-Limit"] = str(info["limit"])
    response["X-RateLimit-Remaining"] = str(info["remaining"])
    response["X-RateLimit-Reset"] = str(info["reset"])
    return response
