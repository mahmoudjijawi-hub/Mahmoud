"""أمر زرع المدير الأولي واشتراك المعهد من متغيرات البيئة."""
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser, Manager
from core.models import Subscription


class Command(BaseCommand):
    help = "يزرع مدير المعهد الأولي وسجل الاشتراك من متغيرات البيئة."

    @transaction.atomic
    def handle(self, *args, **options):
        special = str(settings.ADMIN_SPECIAL_NUMBER)
        username = settings.ADMIN_USERNAME
        password = settings.ADMIN_PASSWORD
        first_name = settings.ADMIN_FIRST_NAME
        last_name = settings.ADMIN_LAST_NAME

        user, created = CustomUser.objects.get_or_create(
            special_number=special,
            defaults={
                "username": username,
                "first_name": first_name[:15],
                "last_name": last_name[:15],
                "role": CustomUser.ROLE_MANAGER,
                "user_type": "1",
                "is_staff": False,
                "is_superuser": False,
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS("تم إنشاء مستخدم المدير الأولي."))
        else:
            # نزامن كلمة المرور واسم المستخدم من .env حتى تطابق الواجهة/البوستمان بعد أي إعادة زرع
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            user.set_password(password)
            user.save()
            if changed:
                self.stdout.write(self.style.SUCCESS("تم تحديث اسم مستخدم وكلمة مرور المدير من البيئة."))
            else:
                self.stdout.write(self.style.SUCCESS("تم مزامنة كلمة مرور المدير من البيئة."))

        Manager.objects.get_or_create(
            user=user,
            defaults={
                "first_name": user.first_name or first_name[:15],
                "last_name": user.last_name or last_name[:15],
                "special_number": special[:7],
                "user_type": "1",
            },
        )

        from academics.models import Stage, Subject, Section

        for stage_name in (
            "بكالوريا",
            "حادي عشر",
            "انتقالي",
            "علمي",
            "أدبي",
            "عاشر",
            "تاسع",
            "ثامن",
            "سابع",
        ):
            Stage.objects.get_or_create(name=stage_name)

        for subject_name in (
            "رياضيات",
            "علوم",
            "فيزياء",
            "كيمياء",
            "عربي",
            "وطنية",
            "ديانة",
            "انكليزي",
            "فرنسي",
            "جغرافيا",
            "تاريخ",
            "فلسفة",
        ):
            Subject.objects.get_or_create(name=subject_name)

        bac = Stage.objects.filter(name="بكالوريا").first()
        if bac:
            for section_name in (
                "الشعبة الأولى",
                "الشعبة الثانية",
                "الشعبة الثالثة",
                "الشعبة الرابعة",
                "الشعبة الخامسة",
            ):
                Section.objects.get_or_create(name=section_name, stage=bac)

        expiry = datetime.strptime(settings.SUBSCRIPTION_EXPIRY_DATE, "%Y-%m-%d").date()
        if not Subscription.objects.exists():
            Subscription.objects.create(expiry_date=expiry, is_active=True)
            self.stdout.write(self.style.SUCCESS("تم إنشاء سجل الاشتراك."))
        else:
            self.stdout.write("سجل الاشتراك موجود مسبقاً.")
