from rest_framework import serializers

from academics.models import Student
from attendance.models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.filter(is_active=True))
    Date = serializers.DateField()
    Status = serializers.ChoiceField(choices=Attendance.STATUS_CHOICES)

    class Meta:
        model = Attendance
        fields = ("id", "student", "Date", "Status", "stage", "section")
        read_only_fields = ("id",)
