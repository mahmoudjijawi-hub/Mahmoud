"""معالج أخطاء API: لا يكشف تفاصيل داخلية للمستخدم النهائي."""
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """يغلف أخطاء DRF مع الإبقاء على بنية التفاصيل القياسية."""
    # استدعاء المعالج الافتراضي أولاً
    response = exception_handler(exc, context)
    # إن لم يُنتج DRF استجابة نترك Django يتصرف (لن يحدث عادة داخل الـ API)
    if response is None:
        return None
    return response
