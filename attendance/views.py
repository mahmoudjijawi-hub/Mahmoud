from rest_framework import viewsets
from rest_framework.response import Response

from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer
from core.permissions import IsManagerOrReadOnlyAuthenticated


def _sync_attendance_from_timetable(student):
    """حصص time_table القديمة بلا سجل حضور تظهر كـ حضور في شاشة الطالب."""
    from schedule.models import TimeTable

    seen_days = set()
    for row in TimeTable.objects.filter(student=student).order_by("Day", "-Hour"):
        if row.Day in seen_days:
            continue
        seen_days.add(row.Day)
        Attendance.objects.get_or_create(
            student=student,
            Date=row.Day,
            defaults={"Status": Attendance.STATUS_PRESENT},
        )


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def paginate_queryset(self, queryset):
        params = self.request.query_params
        if params.get("page") or params.get("page_size"):
            return super().paginate_queryset(queryset)
        return None

    def list(self, request, *args, **kwargs):
        """الفرونت يتوقع مصفوفة: response.data.results || response.data."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(list(queryset), many=True)
        return Response(serializer.data)

    def get_queryset(self):
        qs = Attendance.objects.select_related("student", "stage", "section").all()
        user = self.request.user
        params = self.request.query_params
        student_ref = (
            params.get("student_id")
            or params.get("studentId")
            or params.get("student")
        )
        target = None
        if user.role == "student":
            target = getattr(user, "student_profile", None)
            if target is None:
                return qs.none()
        elif student_ref:
            from schedule.views import _resolve_student_ref

            target = _resolve_student_ref(student_ref)
            if target is None:
                return qs.none()

        if target is not None:
            _sync_attendance_from_timetable(target)
            qs = qs.filter(student=target)
        return qs.order_by("-Date", "-id")
