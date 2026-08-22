"""تحرير الأرقام المميزة وأسماء المستخدم المحجوزة لسجلات غير نشطة."""
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
    يحذف نهائياً أي طالب/أستاذ/مستخدم غير نشط يحجز الرقم أو username s{n}/t{n}.
    إن كان الرقم مستخدماً لحساب نشط (غير المستثنى) يُرجع False.
    """
    special = str(special).strip()
    if not special:
        return True

    active_users = CustomUser.objects.filter(special_number=special, is_active=True)
    if exclude_user_id:
        active_users = active_users.exclude(pk=exclude_user_id)
    if active_users.exists():
        return False

    active_students = Student.objects.filter(special_number=special, is_active=True)
    if exclude_student_id:
        active_students = active_students.exclude(pk=exclude_student_id)
    if active_students.exists():
        return False

    if role == "teacher":
        teachers = Teacher.objects.filter(special_number=special).select_related("user")
        if exclude_teacher_id:
            teachers = teachers.exclude(pk=exclude_teacher_id)
        for teacher in teachers:
            if teacher.user.is_active:
                return False

    # طلاب غير نشطين ما زالوا يحملون الرقم (بقايا soft-delete)
    for student in Student.objects.filter(special_number=special, is_active=False).select_related(
        "user"
    ):
        user = student.user
        student.delete()
        if user is not None:
            CustomUser.objects.filter(pk=user.pk, is_active=False).delete()

    # مستخدمون غير نشطين بنفس الرقم
    CustomUser.objects.filter(special_number=special, is_active=False).delete()

    # username محجوز من حسابات قديمة غير نشطة
    prefix = "t" if role == "teacher" else "s"
    username = f"{prefix}{special}"[:25]
    for user in list(CustomUser.objects.filter(username=username, is_active=False)):
        if hasattr(user, "student_profile"):
            try:
                user.student_profile.delete()
            except Exception:
                pass
        if hasattr(user, "teacher_profile"):
            try:
                user.teacher_profile.delete()
            except Exception:
                pass
        user.delete()

    return True


def allocate_username(prefix, special):
    """اسم مستخدم فريد: s12 أو s12_ab12cd إن كان محجوزاً."""
    base = f"{prefix}{special}"[:25]
    if not CustomUser.objects.filter(username=base).exists():
        return base
    for _ in range(8):
        candidate = f"{prefix}{special}_{uuid.uuid4().hex[:4]}"[:25]
        if not CustomUser.objects.filter(username=candidate).exists():
            return candidate
    return f"{prefix}{uuid.uuid4().hex[:10]}"[:25]
