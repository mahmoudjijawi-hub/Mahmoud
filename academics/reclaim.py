"""تحرير الأرقام المميزة وأسماء المستخدم المحجوزة قبل إنشاء طالب/أستاذ."""
import uuid

from django.db import transaction

from accounts.models import CustomUser
from academics.models import Student, Teacher


@transaction.atomic
def reclaim_special_number(
    special,
    role="student",
    exclude_student_id=None,
    exclude_teacher_id=None,
    exclude_user_id=None,
):
    """
    يحذف نهائياً أي مستخدم معطّل يحجز الرقم أو اسم المستخدم s{n}/t{n}.
    إن كان الرقم مستخدماً لسجل حقيقي (غير المستثنى) يُرجع False.
    """
    special = str(special).strip()
    if not special:
        return True

    # حسابات معطّلة قديمة تحجز الرقم: تُحذف نهائياً
    _purge_disabled_users(CustomUser.objects.filter(special_number=special, is_active=False))

    taken_users = CustomUser.objects.filter(special_number=special)
    if exclude_user_id:
        taken_users = taken_users.exclude(pk=exclude_user_id)
    if taken_users.exists():
        return False

    taken_students = Student.objects.filter(special_number=special)
    if exclude_student_id:
        taken_students = taken_students.exclude(pk=exclude_student_id)
    if taken_students.exists():
        return False

    if role == "teacher":
        teachers = Teacher.objects.filter(special_number=special)
        if exclude_teacher_id:
            teachers = teachers.exclude(pk=exclude_teacher_id)
        if teachers.exists():
            return False

    # اسم مستخدم محجوز من حساب معطّل قديم
    prefix = "t" if role == "teacher" else "s"
    _purge_disabled_users(
        CustomUser.objects.filter(username=f"{prefix}{special}"[:25], is_active=False)
    )
    return True


def _purge_disabled_users(queryset):
    """حذف نهائي لمستخدمين معطّلين مع ملفاتهم المرتبطة."""
    for user in list(queryset.exclude(role=CustomUser.ROLE_MANAGER)):
        Student.objects.filter(user=user).delete()
        Teacher.objects.filter(user=user).delete()
        user.delete()


def allocate_username(prefix, special):
    """اسم مستخدم فريد: s12 أو s12_ab12 إن كان محجوزاً."""
    base = f"{prefix}{special}"[:25]
    if not CustomUser.objects.filter(username=base).exists():
        return base
    for _ in range(8):
        candidate = f"{prefix}{special}_{uuid.uuid4().hex[:4]}"[:25]
        if not CustomUser.objects.filter(username=candidate).exists():
            return candidate
    return f"{prefix}{uuid.uuid4().hex[:10]}"[:25]
