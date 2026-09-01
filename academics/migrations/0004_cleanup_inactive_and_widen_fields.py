"""تنظيف بقايا soft-delete وتوسيع حقول العنوان."""
from django.db import migrations, models


def purge_inactive_students(apps, schema_editor):
    """حذف نهائي لكل طالب/مستخدم غير نشط حتى تتحرر الأرقام 1 و2 و333 وغيرها."""
    Student = apps.get_model("academics", "Student")
    CustomUser = apps.get_model("accounts", "CustomUser")

    for student in Student.objects.filter(is_active=False).iterator():
        user_id = student.user_id
        student.delete()
        CustomUser.objects.filter(pk=user_id, is_active=False).delete()

    # مستخدمو طلاب غير نشطين بلا ملف أو متبقون
    CustomUser.objects.filter(role="student", is_active=False).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0003_seed_catalog"),
        ("accounts", "0003_fix_admin_password"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="address",
            field=models.CharField(max_length=100, verbose_name="عنوان السكن"),
        ),
        migrations.AlterField(
            model_name="student",
            name="personal_notes",
            field=models.CharField(
                blank=True, default="", max_length=100, verbose_name="ملاحظات"
            ),
        ),
        migrations.RunPython(purge_inactive_students, noop_reverse),
    ]
