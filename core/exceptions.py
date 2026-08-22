"""معالج أخطاء API: لا يكشف تفاصيل داخلية للمستخدم النهائي."""
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """يغلف أخطاء DRF مع الإبقاء على بنية التفاصيل القياسية."""
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
    return response
