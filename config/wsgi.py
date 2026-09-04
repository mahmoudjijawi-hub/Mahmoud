"""إعداد WSGI لتشغيل المنصة خلف gunicorn أو خادم تطوير Django."""
# تحديد وحدة الإعدادات قبل إنشاء التطبيق
import os
# استيراد دالة إنشاء تطبيق WSGI
from django.core.wsgi import get_wsgi_application

# ربط التطبيق بإعدادات config.settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# إنشاء كائن التطبيق الذي يقرأه الخادم
application = get_wsgi_application()
try:
    from core.boot import prepare_runtime

    prepare_runtime()
except Exception:
    pass
