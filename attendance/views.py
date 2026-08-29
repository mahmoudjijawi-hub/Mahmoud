from rest_framework import viewsets

from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer
from core.permissions import IsManagerOrReadOnlyAuthenticated


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def paginate_queryset(self, queryset):
        params = self.request.query_params
        if params.get("page") or params.get("page_size"):
            return super().paginate_queryset(queryset)
        return None

    def get_queryset(self):
        qs = Attendance.objects.select_related("student", "stage", "section").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user)
        student_ref = (
            self.request.query_params.get("student_id")
            or self.request.query_params.get("studentId")
            or self.request.query_params.get("student")
        )
        if student_ref:
            from schedule.views import _resolve_student_ref

            student = _resolve_student_ref(student_ref)
            if student is not None:
                qs = qs.filter(student=student)
        return qs
