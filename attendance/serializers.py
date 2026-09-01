from rest_framework import serializers

from academics.models import Student
from attendance.models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    Date = serializers.DateField()
    Status = serializers.ChoiceField(choices=Attendance.STATUS_CHOICES)
    subject = serializers.CharField(max_length=30, required=False, allow_blank=True)

    class Meta:
        model = Attendance
        fields = ("id", "student", "Date", "Status", "subject", "stage", "section")
        read_only_fields = ("id",)

    def to_internal_value(self, data):
        from attendance.models import attendance_subject_key

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
        raw_subject = data.get("subject")
        if raw_subject in (None, ""):
            raw_subject = data.get("Subject") or data.get("subject_name")
        data["subject"] = attendance_subject_key(raw_subject)
        return super().to_internal_value(data)

    def create(self, validated_data):
        from attendance.models import attendance_subject_key

        validated_data["subject"] = attendance_subject_key(validated_data.get("subject"))
        existing = Attendance.objects.filter(
            student=validated_data["student"],
            Date=validated_data["Date"],
            subject=validated_data["subject"],
        ).first()
        if existing is not None:
            return self.update(existing, validated_data)
        return super().create(validated_data)

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
    """المادة المحفوظة على السجل، أو من حصة time_table إن كان السجل قديماً."""
    from attendance.models import attendance_subject_key
    from schedule.models import TimeTable

    stored = attendance_subject_key(getattr(instance, "subject", ""))
    if stored:
        return stored
    row = (
        TimeTable.objects.filter(student=instance.student, Day=instance.Date)
        .order_by("-Hour")
        .first()
    )
    return attendance_subject_key(row.Subject) if row is not None else ""
