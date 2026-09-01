#!/usr/bin/env python
"""نقطة تشغيل أوامر إدارة Django لمنصة المعاهد."""
# استيراد أدوات النظام لتحديد المسارات
import os
# استيراد تنفيذ الأوامر من سطر الأوامر
import sys


# الدالة الرئيسية التي تشغّل أوامر manage.py
def main():
    # تعيين إعدادات المشروع الافتراضية قبل أي استيراد لـ Django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        # استيراد منفّذ أوامر Django
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # إظهار خطأ واضح إذا لم تكن البيئة الافتراضية مفعّلة
        raise ImportError(
            "تعذر استيراد Django. تأكد من تفعيل البيئة الافتراضية وتثبيت المتطلبات."
        ) from exc
    # تمرير وسائط سطر الأوامر إلى Django
    execute_from_command_line(sys.argv)


# تشغيل الدالة فقط عند استدعاء الملف مباشرة
if __name__ == "__main__":
    main()
