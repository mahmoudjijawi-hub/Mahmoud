"""مسلسلات time_table و programs بأسماء حقول الـ Collection والواجهة."""
import re
from datetime import datetime, time

from rest_framework import serializers

from academics.models import Student, Teacher
from schedule.models import TimeTable, Program


def _first(data, *keys):
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        value = lowered.get(str(key).lower())
        if value not in (None, ""):
            return value
    return None


class FlexibleTimeField(serializers.TimeField):
    """يقبل 17:50:51 أو ناتج toLocaleTimeString من المتصفح."""

    def to_internal_value(self, data):
        if data in (None, ""):
            return datetime.now().time().replace(microsecond=0)
        if isinstance(data, time):
            return data
        text = str(data).strip()
        match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if match:
            hour = int(match.group(1)) % 24
            minute = int(match.group(2))
            second = int(match.group(3) or 0)
            text = f"{hour:02d}:{minute:02d}:{second:02d}"
        return super().to_internal_value(text)


class TimeTableSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Student.objects.all(),
        required=False,
    )
    Day = serializers.DateField(required=False)
    Hour = FlexibleTimeField(required=False)
    Subject = serializers.CharField(max_length=30)
    Teacher = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TimeTable
        fields = ("id", "student", "Day", "Hour", "Subject", "Teacher")
        read_only_fields = ("id",)

    def to_internal_value(self, data):
        if hasattr(data, "items"):
            data = {k: v for k, v in data.items()}
        else:
            data = dict(data or {})

        day = _first(data, "Day", "day", "date", "Date")
        if day is not None:
            data["Day"] = day
        elif "Day" not in data:
            data["Day"] = datetime.now().date().isoformat()

        hour = _first(data, "Hour", "hour", "time")
        if hour is not None:
            data["Hour"] = hour

        subject = _first(data, "Subject", "subject", "subject_name", "subjectName")
        if subject is not None:
            data["Subject"] = subject

        teacher = _first(data, "Teacher", "teacher", "teacher_id", "teacherId")
        if teacher is not None:
            try:
                exists = Teacher.objects.filter(pk=teacher).exists()
            except (TypeError, ValueError):
                exists = False
            data["Teacher"] = teacher if exists else None
        else:
            data["Teacher"] = None

        students = _first(data, "student", "students", "student_ids")
        if students is not None and not isinstance(students, (list, tuple)):
            data["student"] = [students]
        elif isinstance(students, (list, tuple)):
            data["student"] = list(students)

        return super().to_internal_value(data)

    def create(self, validated_data):
        instance = super().create(validated_data)
        self._record_attendance(instance)
        return instance

    def _record_attendance(self, instance):
        """شاشة الحضور تستخدم /api/time_table/ — نكتب سجلات حضور للطلاب المحددين."""
        from attendance.models import Attendance

        for student in instance.student.all():
            Attendance.objects.update_or_create(
                student=student,
                Date=instance.Day,
                defaults={"Status": Attendance.STATUS_PRESENT},
            )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["day"] = data.get("Day")
        data["hour"] = data.get("Hour")
        data["subject"] = data.get("Subject")
        data["teacher"] = data.get("Teacher")
        return data


class ProgramSerializer(serializers.ModelSerializer):
    certificate_type = serializers.CharField(max_length=40)
    grade = serializers.CharField(max_length=30)
    section = serializers.CharField(max_length=40)
    day = serializers.CharField(max_length=20)
    time_slot = serializers.CharField(max_length=20)
    room = serializers.CharField(max_length=40)
    subject_name = serializers.CharField(max_length=30)
    teacher_name = serializers.PrimaryKeyRelatedField(
        queryset=Teacher.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Program
        fields = (
            "id",
            "certificate_type",
            "grade",
            "section",
            "day",
            "time_slot",
            "room",
            "subject_name",
            "teacher_name",
        )
        read_only_fields = ("id",)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["day"] = _arabic_weekday(data.get("day"))
        data["time_slot"] = _normalize_time_slot(data.get("time_slot"))
        data["hour"] = data["time_slot"]
        data["subject"] = data.get("subject_name")
        return data


_WEEKDAY_AR = {
    "sunday": "الأحد",
    "monday": "الاثنين",
    "tuesday": "الثلاثاء",
    "wednesday": "الأربعاء",
    "thursday": "الخميس",
    "friday": "الجمعة",
    "saturday": "السبت",
    "الأحد": "الأحد",
    "الاثنين": "الاثنين",
    "الثلاثاء": "الثلاثاء",
    "الأربعاء": "الأربعاء",
    "الخميس": "الخميس",
    "الجمعة": "الجمعة",
    "السبت": "السبت",
}


def _arabic_weekday(value):
    text = str(value or "").strip()
    if not text:
        return text
    return _WEEKDAY_AR.get(text.lower(), _WEEKDAY_AR.get(text, text))


def _normalize_time_slot(value):
    text = str(value or "").strip()
    if not text:
        return text
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return text
    return f"{int(match.group(1)):02d}:{match.group(2)}"
