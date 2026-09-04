"""وسطاء الاشتراك وجلسة المدير الواحدة وإصلاح مسار الـ API."""
from datetime import date

from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth import logout

from core.models import Subscription


# مسارات تُستثنى من فحص الاشتراك حتى تظهر رسالة الدخول بوضوح
_EXEMPT_PREFIXES = (
    "/api/token",
    "/api/student-login",
    "/api/student_login",
    "/api/student-detail",
    "/api/student_detail",
    "/static",
    "/media",
)


class ForceHttpsBehindProxyMiddleware:
    """
    يضمن اعتبار الطلب HTTPS خلف Render/nginx عندما IS_HTTPS=True.
    يمنع SecurityMiddleware من إرجاع 301 على POST /api/payments فيضيع الجسم
    ويفشل زر الدفع في المتصفح.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "IS_HTTPS", False):
            forwarded = (request.META.get("HTTP_X_FORWARDED_PROTO") or "").split(",")[0].strip()
            if forwarded != "https":
                request.META["HTTP_X_FORWARDED_PROTO"] = "https"
            # بعض الإصدارات تقرأ wsgi.url_scheme مباشرة
            request.META["wsgi.url_scheme"] = "https"
        return self.get_response(request)


class ApiTrailingSlashMiddleware:
    """
    يمنع ضياع جسم POST عند نسيان الشرطة المائلة في مسارات /api/.
    بدل إعادة توجيه 301 (التي تحول POST إلى GET عند كثير من العملاء)
    نُعيد كتابة المسار داخلياً بإضافة /.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or request.path or ""
        if path.startswith("/api/") and not path.endswith("/"):
            # لا نلمس مسارات الملفات ذات الامتداد
            last = path.rsplit("/", 1)[-1]
            if "." not in last:
                new_path = path + "/"
                request.path_info = new_path
                request.path = new_path
                # بعض الخوادم تقرأ PATH_INFO من META بعد الوسطاء
                request.META["PATH_INFO"] = new_path
        return self.get_response(request)


class SubscriptionMiddleware:
    """يمنع استخدام المنصة إذا انتهى الاشتراك أو أُوقف يدوياً."""

    def __init__(self, get_response):
        # حفظ سلسلة الوسطاء التالية
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        # السماح لمسار الإدارة العشوائي حتى يمكن تمديد الاشتراك يدوياً
        admin_prefix = "/" + __import__("django.conf").conf.settings.ADMIN_URL
        if path.startswith(admin_prefix):
            return self.get_response(request)
        # السماح بمسارات التوكن والملفات الثابتة
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return self.get_response(request)
        # لا فحص على الجذر الفارغ غير الـ API
        if not path.startswith("/api/"):
            return self.get_response(request)
        # جلب سجل الاشتراك الوحيد إن وُجد
        subscription = Subscription.objects.order_by("id").first()
        if subscription is None:
            # إن لم يُزرع الاشتراك بعد نسمح بالعمل حتى لا تُكسر الهجرة الأولية
            return self.get_response(request)
        expired = subscription.expiry_date < date.today()
        if (not subscription.is_active) or expired:
            # رسالة عربية واضحة بدل 403 عام
            return JsonResponse(
                {
                    "detail": "انتهت صلاحية اشتراك هذا المعهد، يرجى التواصل مع الدعم",
                },
                status=403,
            )
        return self.get_response(request)


class SingleManagerSessionMiddleware:
    """
    يضمن جلسة Django واحدة نشطة لحساب المدير (لوحة /admin/).
    إن وُجدت جلسة أقدم لا تطابق last_session_key تُغلق فوراً.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        # نطبّق الفحص فقط على مدير مصادق عبر الجلسة (ليس JWT)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "role", None) == "manager"
            and getattr(user, "last_session_key", None)
        ):
            current_key = request.session.session_key
            # إن وُجدت جلسة حالية مختلفة عن المفتاح المخزن نُخرج المستخدم
            if current_key and current_key != user.last_session_key:
                logout(request)
        return self.get_response(request)


class AdminLoginLockoutMiddleware:
    """
    قفل POST لدخول لوحة الإدارة ومسار توكن الواجهة بعد 5 محاولات فاشلة.
    العداد في الـ cache لكل IP (مع تخزين IP/اسم المستخدم)، ويُصفَّر عند النجاح أو بعد دقيقتين.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from core.admin_login_limit import (
            current_state,
            is_admin_login_path,
            is_api_login_path,
            is_special_number_only,
            rate_limit_headers,
            register_failure,
            register_success,
        )

        if is_admin_login_path(request):
            return self._handle(request, json_only=False)

        if is_api_login_path(request) and request.method == "POST" and not is_special_number_only(
            request
        ):
            return self._handle(request, json_only=True)

        return self.get_response(request)

    def _handle(self, request, json_only):
        from core.admin_login_limit import (
            current_state,
            rate_limit_headers,
            register_failure,
            register_success,
        )

        if request.method == "POST":
            blocked, wait, remaining = current_state(request)
            if blocked:
                return _login_lock_response(request, wait, json_only=json_only)

        response = self.get_response(request)
        if request.method != "POST":
            blocked, wait, remaining = current_state(request)
            for key, value in rate_limit_headers(remaining, wait).items():
                response[key] = value
            return response

        if response.status_code in (301, 302, 303) or _response_issued_token(response):
            register_success(request)
            for key, value in rate_limit_headers(5, 0).items():
                response[key] = value
            return response

        if _is_special_number_ok(response):
            return response

        blocked, wait, remaining = register_failure(request)
        if blocked:
            return _login_lock_response(request, wait, json_only=json_only)
        for key, value in rate_limit_headers(remaining, 0).items():
            response[key] = value
        return response


def _response_payload(response):
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    try:
        import json

        loaded = json.loads(response.content.decode("utf-8") or "{}")
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _response_issued_token(response):
    if getattr(response, "status_code", None) != 200:
        return False
    data = _response_payload(response)
    return bool(data.get("access") or data.get("token") or data.get("accessToken"))


def _is_special_number_ok(response):
    if getattr(response, "status_code", None) != 200:
        return False
    data = _response_payload(response)
    return bool(data.get("requires_password")) and not (
        data.get("access") or data.get("token") or data.get("accessToken")
    )


def _login_lock_response(request, wait, json_only=False):
    from django.contrib import admin
    from django.contrib.admin.forms import AdminAuthenticationForm
    from django.http import JsonResponse
    from django.template.response import TemplateResponse

    from core.admin_login_limit import LOCK_MESSAGE, lock_json_payload, rate_limit_headers

    wait = max(int(wait or 120), 1)
    accept = (request.META.get("HTTP_ACCEPT") or "").lower()
    first_accept = accept.split(",")[0]
    wants_json = (
        json_only
        or "application/json" in first_accept
        or request.content_type == "application/json"
    )
    if wants_json:
        response = JsonResponse(
            lock_json_payload(wait),
            status=429,
            json_dumps_params={"ensure_ascii": False},
        )
    else:
        form = AdminAuthenticationForm(request, data=request.POST or None)
        form.add_error(None, LOCK_MESSAGE)
        context = {
            **admin.site.each_context(request),
            "title": "تسجيل الدخول",
            "app_path": request.get_full_path(),
            "form": form,
            "username": request.POST.get("username", "") if request.method == "POST" else "",
        }
        response = TemplateResponse(request, "admin/login.html", context, status=429)
        response.render()
    response["Retry-After"] = str(wait)
    for key, value in rate_limit_headers(0, wait).items():
        response[key] = value
    return response
