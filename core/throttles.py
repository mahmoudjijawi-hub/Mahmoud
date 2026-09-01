"""حدود معدّل الطلبات لمنع التخمين بالقوة الغاشمة على الدخول والرقم المميز."""
from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    """حد صارم لتسجيل دخول المدير باسم المستخدم وكلمة المرور."""

    scope = "login"


class SpecialNumberRateThrottle(ScopedRateThrottle):
    """حد صارم جداً على مسار الرقم المميز لأنه قصير وقابل للتخمين."""

    scope = "special_number"


class PaymentRateThrottle(ScopedRateThrottle):
    """حد خاص بنقاط الدفع لتقليل الإساءة."""

    scope = "payments"
