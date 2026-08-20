from rest_framework import viewsets

from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer
from core.permissions import IsManagerOrReadOnlyAuthenticated


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Attendance.objects.select_related("student", "stage", "section").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user)
        return qs
