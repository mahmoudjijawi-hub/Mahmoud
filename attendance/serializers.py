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
        raw_status = data.get("Status")
        if raw_status in (None, ""):
            raw_status = data.get("status") or data.get("attendance_status")
        mapped = _normalize_status(raw_status, data.get("is_present"))
        if mapped:
            data["Status"] = mapped
        if data.get("Date") in (None, ""):
            data["Date"] = data.get("date") or data.get("day") or data.get("session_date")
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
        data["Subject"] = subject
        return data


def _normalize_status(raw_status, is_present):
    if raw_status not in (None, ""):
        key = str(raw_status).strip().lower()
        aliases = {
            "حضور": Attendance.STATUS_PRESENT,
            "غياب": Attendance.STATUS_ABSENT,
            "present": Attendance.STATUS_PRESENT,
            "absent": Attendance.STATUS_ABSENT,
            "true": Attendance.STATUS_PRESENT,
            "false": Attendance.STATUS_ABSENT,
        }
        if key in aliases:
            return aliases[key]
        return str(raw_status).strip()
    if is_present is True:
        return Attendance.STATUS_PRESENT
    if is_present is False:
        return Attendance.STATUS_ABSENT
    return None


def _attendance_subject(instance):
    """المادة من حصة time_table لنفس الطالب والتاريخ إن وُجدت."""
    from schedule.models import TimeTable

    row = (
        TimeTable.objects.filter(student=instance.student, Day=instance.Date)
        .order_by("-Hour")
        .first()
    )
    return (row.Subject or "").strip() if row is not None else ""
