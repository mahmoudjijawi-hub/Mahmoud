"""تسجيل تطبيق الحسابات وربط إشارات تسجيل الدخول."""
import sys

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default = True
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "الحسابات"

    def ready(self):
        # ربط إشارات جلسة المدير وسجل الدخول عند تحميل التطبيق
        from accounts import signals  # noqa: F401

        # لا نزامن أثناء أوامر الهجرة حتى لا تفشل قبل إنشاء الجداول
        if any(cmd in sys.argv for cmd in ("migrate", "makemigrations", "test")):
            return
        try:
            from accounts.bootstrap import ensure_admin_credentials

            ensure_admin_credentials()
        except Exception:
            # لا نكسر إقلاع السيرفر إن فشلت المزامنة لسبب عابر
            pass
