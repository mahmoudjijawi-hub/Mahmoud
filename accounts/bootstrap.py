"""ضمان وجود مدير أولي بكلمة مرور صالحة مطابقة للإعدادات — يُستدعى عند الإقلاع."""
import logging

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

logger = logging.getLogger("accounts.auth")

# كلمات مرور مقبولة تاريخياً حتى لا ينكسر الدخول بعد تغيّر .env
KNOWN_ADMIN_PASSWORDS = (
    "ammar12345ammar",
    "change-this-password",
    "password123",
)


def ensure_admin_credentials():
    """
    ينشئ/يصلح حساب المدير من ADMIN_* في الإعدادات.
    إن وُجد الحساب بكلمة مرور غير مطابقة يُعاد ضبطها فوراً.
    """
    try:
        from accounts.models import CustomUser, Manager
    except Exception:
        return

    username = str(getattr(settings, "ADMIN_USERNAME", "ammar") or "ammar")[:25]
    password = str(getattr(settings, "ADMIN_PASSWORD", "ammar12345ammar") or "ammar12345ammar")
    special = str(getattr(settings, "ADMIN_SPECIAL_NUMBER", "7788990") or "7788990")[:10]
    first_name = str(getattr(settings, "ADMIN_FIRST_NAME", "مدير") or "مدير")[:15]
    last_name = str(getattr(settings, "ADMIN_LAST_NAME", "المعهد") or "المعهد")[:15]

    try:
        user = (
            CustomUser.objects.filter(special_number=special).first()
            or CustomUser.objects.filter(username__iexact=username).first()
        )
        if user is None:
            user = CustomUser.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                special_number=special,
                role=CustomUser.ROLE_MANAGER,
                user_type="1",
                is_active=True,
            )
            logger.info("bootstrap_admin created")
        else:
            needs_save = False
            if user.username != username:
                user.username = username
                needs_save = True
            if user.special_number != special:
                user.special_number = special
                needs_save = True
            if user.role != CustomUser.ROLE_MANAGER:
                user.role = CustomUser.ROLE_MANAGER
                needs_save = True
            if not user.is_active:
                user.is_active = True
                needs_save = True
            if user.user_type != "1":
                user.user_type = "1"
                needs_save = True
            # دائماً نزامن كلمة المرور مع الإعدادات حتى ينجح دخول الفرونت
            if (not user.has_usable_password()) or (not user.check_password(password)):
                user.set_password(password)
                needs_save = True
                logger.info("bootstrap_admin password_synced")
            if needs_save:
                user.first_name = user.first_name or first_name
                user.last_name = user.last_name or last_name
                user.save()

        Manager.objects.get_or_create(
            user=user,
            defaults={
                "first_name": user.first_name or first_name,
                "last_name": user.last_name or last_name,
                "special_number": special[:7],
                "user_type": "1",
            },
        )
    except (OperationalError, ProgrammingError):
        # الجداول غير جاهزة بعد (أثناء migrate)
        return
