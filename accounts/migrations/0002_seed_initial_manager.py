"""زرع المدير الأولي من متغيرات البيئة — الرقم المميز ليس hardcoded."""
from django.conf import settings
from django.db import migrations


def seed_initial_manager(apps, schema_editor):
    # جلب النماذج التاريخية للهجرة
    CustomUser = apps.get_model("accounts", "CustomUser")
    Manager = apps.get_model("accounts", "Manager")
    special = str(getattr(settings, "ADMIN_SPECIAL_NUMBER", "") or "").strip()
    # إن لم يُضبط المتغير نتخطى الزرع
    if not special:
        return
    username = getattr(settings, "ADMIN_USERNAME", "ammar")
    first_name = str(getattr(settings, "ADMIN_FIRST_NAME", "مدير"))[:15]
    last_name = str(getattr(settings, "ADMIN_LAST_NAME", "المعهد"))[:15]
    password = str(getattr(settings, "ADMIN_PASSWORD", "ammar12345ammar") or "ammar12345ammar")
    # لا نكرر الزرع إن وُجد المستخدم
    if CustomUser.objects.filter(special_number=special).exists():
        return
    from django.contrib.auth.hashers import make_password

    user = CustomUser(
        username=username[:25],
        first_name=first_name,
        last_name=last_name,
        special_number=special[:10],
        role="manager",
        user_type="1",
        is_active=True,
        is_staff=False,
        is_superuser=False,
        # تجزئة كلمة المرور مباشرة حتى ينجح الدخول بعد migrate بدون seed_manager
        password=make_password(password),
    )
    user.save()
    Manager.objects.create(
        user=user,
        first_name=first_name,
        last_name=last_name,
        special_number=special[:7],
        user_type="1",
    )


def unseed_initial_manager(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    special = str(getattr(settings, "ADMIN_SPECIAL_NUMBER", "") or "").strip()
    if special:
        CustomUser.objects.filter(special_number=special, is_superuser=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_initial_manager, unseed_initial_manager),
    ]
