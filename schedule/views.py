"""واجهات /api/time_table/ و /api/programs/."""
from rest_framework import viewsets

from core.permissions import IsManagerOrReadOnlyAuthenticated
from schedule.models import TimeTable, Program
from schedule.serializers import TimeTableSerializer, ProgramSerializer


class TimeTableViewSet(viewsets.ModelViewSet):
    serializer_class = TimeTableSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = TimeTable.objects.select_related("Teacher").prefetch_related("student").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user).distinct()
        if user.role == "teacher":
            return qs.filter(Teacher__user=user)
        teacher_id = self.request.query_params.get("teacher_id")
        if teacher_id:
            qs = qs.filter(Teacher_id=teacher_id)
        return qs


class ProgramViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Program.objects.select_related("teacher_name").all()
        user = self.request.user
        params = self.request.query_params
        if user.role == "teacher":
            qs = qs.filter(teacher_name__user=user)
        if user.role == "student":
            student = getattr(user, "student_profile", None)
            if student is None:
                return qs.none()
            subjects = [student.class1, student.class2, student.class3]
            qs = qs.filter(subject_name__in=[s for s in subjects if s])
        for key in ("certificate_type", "grade", "section", "day", "time_slot", "room", "subject_name"):
            value = params.get(key)
            if value:
                qs = qs.filter(**{key: value})
        teacher_name = params.get("teacher_name") or params.get("teacher_id")
        if teacher_name:
            qs = qs.filter(teacher_name_id=teacher_name)
        return qs
