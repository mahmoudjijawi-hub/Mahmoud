"""تسجيل تطبيق الحسابات وربط إشارات تسجيل الدخول."""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default = True
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "الحسابات"

    def ready(self):
        # ربط إشارات جلسة المدير وسجل الدخول عند تحميل التطبيق
        from accounts import signals  # noqa: F401
