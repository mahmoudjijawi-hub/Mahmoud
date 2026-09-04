"""معالج أخطاء API: لا يكشف تفاصيل داخلية للمستخدم النهائي."""
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """يغلف أخطاء DRF مع الإبقاء على بنية التفاصيل القياسية."""
    from rest_framework.exceptions import Throttled

    # تعارض فريد في قاعدة البيانات → 400 عربي واضح بدل 500
    if isinstance(exc, IntegrityError):
        return Response(
            {
                "success": False,
                "detail": "تعارض في البيانات: الرقم المميز أو اسم المستخدم مستخدم مسبقاً.",
                "code": "integrity_error",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, Throttled) or (
        isinstance(response.data, dict) and response.data.get("code") == "too_many_requests"
    ):
        wait = int(
            (response.data.get("wait") if isinstance(response.data, dict) else None)
            or getattr(exc, "wait", None)
            or 120
        )
        request = context.get("request") if context else None
        message = "تم تجاوز عدد المحاولات المسموح بها (5 محاولات). تم حظر المحاولة لمدة دقيقتين."
        try:
            from core.admin_login_limit import LOCK_MESSAGE

            message = LOCK_MESSAGE
        except Exception:
            pass
        response.data = {
            "success": False,
            "detail": message,
            "error": message,
            "message": message,
            "non_field_errors": [message],
            "code": "too_many_requests",
            "wait": wait,
            "retry_after": wait,
            "locked": True,
        }
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        response["Retry-After"] = str(wait)
        if request is not None:
            from core.throttles import apply_manager_login_rate_limit_headers

            apply_manager_login_rate_limit_headers(request, response)
    return response
