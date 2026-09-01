"""صلاحيات الأدوار ومنع IDOR على مستوى الكائن."""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsManager(BasePermission):
    """يسمح فقط لحساب دوره manager."""

    message = "هذه العملية متاحة للمدير فقط."

    def has_permission(self, request, view):
        # رفض غير المسجّلين فوراً
        if not request.user or not request.user.is_authenticated:
            return False
        # السماح إن كان الدور مديراً والحساب نشطاً
        return request.user.role == "manager" and request.user.is_active


class IsTeacher(BasePermission):
    """يسمح فقط لحساب دوره teacher."""

    message = "هذه العملية متاحة للأستاذ فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == "teacher" and request.user.is_active


class IsStudent(BasePermission):
    """يسمح فقط لحساب دوره student."""

    message = "هذه العملية متاحة للطالب فقط."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == "student" and request.user.is_active


class IsManagerOrReadOnlyAuthenticated(BasePermission):
    """
    الكتابة للمدير فقط.
    القراءة لأي مستخدم مصادق عليه، على أن تُصفَّى الاستعلامات في الـ ViewSet.
    """

    message = "ليس لديك صلاحية تنفيذ هذه العملية."

    def has_permission(self, request, view):
        # يجب تسجيل الدخول دائماً
        if not request.user or not request.user.is_authenticated:
            return False
        # الحساب غير النشط ممنوع
        if not request.user.is_active:
            return False
        # القراءة مسموحة للجميع المصادقين
        if request.method in SAFE_METHODS:
            return True
        # التعديل/الإنشاء/الحذف للمدير فقط
        return request.user.role == "manager"


class IsStudentOwner(BasePermission):
    """
    الطالب يصل فقط لكائنه أو لكائنات مرتبطة به.
    المدير يتجاوز الفحص. الأستاذ يُسمح بالقراءة إن وُجدت علاقة.
    """

    message = "لا يمكنك الوصول إلى بيانات طالب آخر."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)

    def has_object_permission(self, request, view, obj):
        user = request.user
        # المدير يرى الكل
        if user.role == "manager":
            return True
        # استخراج كائن الطالب من النموذج الحالي
        student = _extract_student(obj)
        if student is None:
            # إن لم يكن الكائن مرتبطاً بطالب، الأستاذ والمدير فقط
            return user.role in ("manager", "teacher")
        # الطالب صاحب السجل فقط
        if user.role == "student":
            return hasattr(user, "student_profile") and student.pk == user.student_profile.pk
        # الأستاذ يقرأ فقط
        if user.role == "teacher":
            return request.method in SAFE_METHODS
        return False


def _extract_student(obj):
    """يرجع نموذج الطالب من الكائن إن وُجد."""
    # الكائن نفسه طالب
    if obj.__class__.__name__ == "Student":
        return obj
    # علاقة واحد لواحد باسم student
    if hasattr(obj, "student") and obj.student is not None:
        related = obj.student
        # إن كانت ManyRelatedManager (M2M) لا نُرجع طالباً واحداً هنا
        if hasattr(related, "all"):
            return None
        return related
    return None
