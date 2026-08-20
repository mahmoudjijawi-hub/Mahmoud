"""إعداد ASGI للتوافق مع الخوادم غير المتزامنة إن لزم لاحقاً."""
# تحديد وحدة الإعدادات قبل إنشاء التطبيق
import os
# استيراد دالة إنشاء تطبيق ASGI
from django.core.asgi import get_asgi_application

# ربط التطبيق بإعدادات config.settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
# إنشاء كائن التطبيق غير المتزامن
application = get_asgi_application()
