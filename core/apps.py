"""تسجيل تطبيق core."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    # نوع المفتاح التلقائي الافتراضي
    default_auto_field = "django.db.models.BigAutoField"
    # اسم التطبيق داخل INSTALLED_APPS
    name = "core"
    # الاسم العربي المعروض في لوحة الإدارة
    verbose_name = "النواة والاشتراك"
