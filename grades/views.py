"""واجهة /api/exams/ المطابقة للـ Collection."""
from rest_framework import viewsets

from core.permissions import IsManagerOrReadOnlyAuthenticated
from grades.models import Exam
from grades.serializers import ExamSerializer


class ExamViewSet(viewsets.ModelViewSet):
    serializer_class = ExamSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Exam.objects.prefetch_related("student").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user).distinct()
        teacher_id = self.request.query_params.get("teacher_id")
        if teacher_id:
            qs = qs.filter(student__isnull=False)
        return qs
