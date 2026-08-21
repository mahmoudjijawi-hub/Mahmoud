"""ضبط كلمة مرور المدير الأولي من البيئة — إصلاح الحساب المزروع بـ password='!'."""
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def set_admin_password(apps, schema_editor):
    # جلب النموذج التاريخي
    CustomUser = apps.get_model("accounts", "CustomUser")
    Manager = apps.get_model("accounts", "Manager")
    special = str(getattr(settings, "ADMIN_SPECIAL_NUMBER", "") or "").strip() or "7788990"
    username = str(getattr(settings, "ADMIN_USERNAME", "ammar") or "ammar")[:25]
    password = str(getattr(settings, "ADMIN_PASSWORD", "ammar12345ammar") or "ammar12345ammar")
    first_name = str(getattr(settings, "ADMIN_FIRST_NAME", "مدير") or "مدير")[:15]
    last_name = str(getattr(settings, "ADMIN_LAST_NAME", "المعهد") or "المعهد")[:15]

    user = CustomUser.objects.filter(special_number=special).first()
    if user is None:
        user = CustomUser.objects.filter(username=username).first()
    if user is None:
        # إنشاء كامل إن لم يوجد (قواعد بلا زرع سابق)
        user = CustomUser(
            username=username,
            first_name=first_name,
            last_name=last_name,
            special_number=special[:10],
            role="manager",
            user_type="1",
            is_active=True,
            is_staff=False,
            is_superuser=False,
            password=make_password(password),
        )
        user.save()
    else:
        # مزامنة بيانات الدخول من .env حتى ينجح POST /api/token/
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.special_number = special[:10]
        user.role = "manager"
        user.user_type = "1"
        user.is_active = True
        user.password = make_password(password)
        user.save()

    Manager.objects.get_or_create(
        user=user,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "special_number": special[:7],
            "user_type": "1",
        },
    )


def noop_reverse(apps, schema_editor):
    # لا نحذف المدير عند التراجع حتى لا نفقد بيانات الإنتاج
    return


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_seed_initial_manager"),
    ]
    operations = [
        migrations.RunPython(set_admin_password, noop_reverse),
    ]
