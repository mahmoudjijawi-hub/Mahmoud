"""وسطاء الاشتراك وجلسة المدير الواحدة."""
from datetime import date

from django.http import JsonResponse
from django.contrib.auth import logout

from core.models import Subscription


# مسارات تُستثنى من فحص الاشتراك حتى تظهر رسالة الدخول بوضوح
_EXEMPT_PREFIXES = (
    "/api/token",
    "/static",
    "/media",
)


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
