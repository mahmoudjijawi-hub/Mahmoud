"""إلغاء الحذف الناعم نهائياً: تنظيف السجلات المعطّلة ثم حذف الحقل."""
from django.db import migrations


def purge_inactive(apps, schema_editor):
    """حذف كل طالب معطّل ومستخدمه حتى لا تبقى أرقام مميزة محجوزة."""
    Student = apps.get_model("academics", "Student")
    CustomUser = apps.get_model("accounts", "CustomUser")

    user_ids = list(
        Student.objects.filter(is_active=False).values_list("user_id", flat=True)
    )
    Student.objects.filter(is_active=False).delete()
    CustomUser.objects.filter(pk__in=user_ids).delete()
    # حسابات طلاب معطّلة بلا ملف مرتبط
    CustomUser.objects.filter(role="student", is_active=False).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0004_cleanup_inactive_and_widen_fields"),
        ("accounts", "0003_fix_admin_password"),
    ]

    operations = [
        migrations.RunPython(purge_inactive, noop_reverse),
        migrations.RemoveField(model_name="student", name="is_active"),
    ]
