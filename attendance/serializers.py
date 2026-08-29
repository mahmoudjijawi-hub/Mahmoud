from rest_framework import serializers

from academics.models import Student
from attendance.models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    Date = serializers.DateField()
    Status = serializers.ChoiceField(choices=Attendance.STATUS_CHOICES)

    class Meta:
        model = Attendance
        fields = ("id", "student", "Date", "Status", "stage", "section")
        read_only_fields = ("id",)

    def to_internal_value(self, data):
        if hasattr(data, "items"):
            data = {k: v for k, v in data.items()}
        else:
            data = dict(data or {})
        if data.get("Status") in (None, "") and data.get("status") not in (None, ""):
            data["Status"] = data.get("status")
        if data.get("Date") in (None, "") and data.get("date") not in (None, ""):
            data["Date"] = data.get("date")
        if data.get("Status") in (None, "") and data.get("is_present") is True:
            data["Status"] = Attendance.STATUS_PRESENT
        if data.get("Status") in (None, "") and data.get("is_present") is False:
            data["Status"] = Attendance.STATUS_ABSENT
        return super().to_internal_value(data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        status = data.get("Status")
        date = data.get("Date")
        subject = _attendance_subject(instance)
        data["status"] = status
        data["attendance_status"] = status
        data["is_present"] = status == Attendance.STATUS_PRESENT
        data["date"] = date
        data["day"] = date
        data["session_date"] = date
        data["subject"] = subject
        data["subject_name"] = subject
        return data


def _attendance_subject(instance):
    """المادة من حصة time_table لنفس الطالب والتاريخ إن وُجدت."""
    from schedule.models import TimeTable

    row = (
        TimeTable.objects.filter(student=instance.student, Day=instance.Date)
        .order_by("-Hour")
        .first()
    )
    return (row.Subject or "").strip() if row is not None else ""
