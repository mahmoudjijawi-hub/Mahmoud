"""واجهات الأساتذة والطلاب المطابقة للـ Collection مع منع IDOR."""
import uuid

from django.db.models import Q
from django.http import FileResponse, Http404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from academics.models import Teacher, Student
from academics.serializers import TeacherSerializer, StudentSerializer, StudentPagination
from core.permissions import IsManagerOrReadOnlyAuthenticated, IsStudentOwner


class TeacherViewSet(viewsets.ModelViewSet):
    """GET/POST /api/teachers/ و PATCH /api/teachers/{uuid}/"""

    serializer_class = TeacherSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    queryset = Teacher.objects.select_related("user").all()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # الأستاذ يرى ملفه فقط
        if user.role == "teacher":
            return qs.filter(user=user)
        # الطالب لا يرى قائمة الأساتذة كاملة — يُصفَّى عبر البرامج لاحقاً
        if user.role == "student":
            return qs.none()
        teacher_id = self.request.query_params.get("teacher_id")
        if teacher_id:
            qs = qs.filter(pk=teacher_id)
        return qs

    @action(detail=True, methods=["get"], url_path="cv")
    def download_cv(self, request, pk=None):
        """تنزيل ملف السيرة عبر مسار محمي بدل رابط ثابت عام."""
        teacher = self.get_object()
        if request.user.role != "manager":
            return Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        if not teacher.cv_file:
            raise Http404("لا يوجد ملف سيرة ذاتية.")
        return FileResponse(teacher.cv_file.open("rb"), as_attachment=True)


class StudentViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/students/
    PATCH/DELETE /api/students/{uuid}/
    البحث بـ special_number أو name/search مع ترقيم الصفحات.
    """

    serializer_class = StudentSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated, IsStudentOwner)
    pagination_class = StudentPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        # الشطب الناعم: نخفي غير النشطين من القوائم
        qs = Student.objects.select_related("user").filter(is_active=True)
        user = self.request.user
        if user.role == "student":
            return qs.filter(user=user)
        if user.role == "teacher":
            return qs
        special = self.request.query_params.get("special_number")
        name = self.request.query_params.get("search") or self.request.query_params.get("name")
        if special:
            qs = qs.filter(special_number=str(special))
        if name:
            qs = qs.filter(Q(first_name__icontains=name) | Q(last_name__icontains=name))
        return qs

    def perform_destroy(self, instance):
        """
        شطب ناعم مع تحرير الرقم المميز واسم المستخدم،
        حتى يمكن إضافة طالب جديد بنفس الرقم (مثل 22) لاحقاً مع بقاء السجلات التاريخية.
        """
        # قيمة فريدة بطول 10 لتفريغ قيد unique على special_number
        released = uuid.uuid4().hex[:10]
        instance.is_active = False
        instance.special_number = released
        instance.save(update_fields=["is_active", "special_number"])
        user = instance.user
        user.is_active = False
        user.special_number = released
        # تحرير username أيضاً لأن الإنشاء يستخدم s{special_number}
        user.username = f"d{released}"[:25]
        user.save(update_fields=["is_active", "special_number", "username"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
