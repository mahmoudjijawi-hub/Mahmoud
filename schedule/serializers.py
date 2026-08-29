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
    room = serializers.CharField(max_length=40, allow_blank=True, required=False)
    subject_name = serializers.CharField(max_length=30, allow_blank=True)
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

    def to_internal_value(self, data):
        if hasattr(data, "items"):
            data = {k: v for k, v in data.items()}
        else:
            data = dict(data or {})

        if data.get("certificate_type") not in (None, ""):
            data["certificate_type"] = _normalize_certificate(data.get("certificate_type"))
        if data.get("day") not in (None, ""):
            data["day"] = _arabic_weekday(data.get("day"))
        if data.get("time_slot") not in (None, ""):
            data["time_slot"] = _normalize_time_slot(data.get("time_slot"))

        teacher = _first(data, "teacher_name", "teacher", "teacher_id", "teacherId")
        if teacher in (None, "", "null"):
            data["teacher_name"] = None
        elif isinstance(teacher, dict):
            data["teacher_name"] = teacher.get("id") or teacher.get("pk")
        else:
            data["teacher_name"] = teacher

        if data.get("room") is None:
            data["room"] = ""
        return super().to_internal_value(data)

    def create(self, validated_data):
        """شاشة المدير: نفس اليوم/الساعة/الشعبة تُحدَّث ولا تُكرَّر."""
        instance = _existing_program_slot(validated_data)
        if instance is not None:
            return self.update(instance, validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        _collapse_duplicate_slots(instance)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["day"] = _arabic_weekday(data.get("day"))
        data["time_slot"] = _normalize_time_slot(data.get("time_slot"))
        data["hour"] = data["time_slot"]
        data["subject"] = data.get("subject_name")
        teacher = getattr(instance, "teacher_name", None)
        teacher_id = str(teacher.pk) if teacher is not None else None
        student = self.context.get("student")
        # شاشة برنامج الطالب تعرض teacher_name كنص؛ محرر المدير يحتاج المعرّف
        if student is not None and teacher is not None:
            data["teacher_id"] = teacher_id
            data["teacher_name"] = f"{teacher.first_name} {teacher.last_name}".strip()
        else:
            data["teacher_name"] = teacher_id
        data["teacher"] = data["teacher_name"]
        data["class3"] = (instance.section or "").strip()
        if student is not None:
            from academics.serializers import student_path_labels

            path = student_path_labels(student)
            data["class1"] = path["class1"]
            data["class3"] = path["class3"] or data["class3"]
        else:
            data["class1"] = _program_class1_label(instance)
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
    "الاحد": "الأحد",
    "الاثنين": "الاثنين",
    "الإثنين": "الاثنين",
    "الثلاثاء": "الثلاثاء",
    "الأربعاء": "الأربعاء",
    "الاربعاء": "الأربعاء",
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
    """08:00 و 8:00 و 8 و ٨ تصبح 08:00 حتى ترتبط خلية الأحد الأولى."""
    from core.digits import normalize_digits

    text = normalize_digits(str(value or "")).strip()
    if not text:
        return text
    match = re.search(r"(\d{1,2})(?::(\d{2}))?", text)
    if not match:
        return text
    return f"{int(match.group(1)) % 24:02d}:{int(match.group(2) or 0):02d}"


_CERT_AR = {
    "baccalaureate": "بكالوريا",
    "eleventh": "حادي عشر",
    "transitional": "تاسع / عاشر",
}


def _program_class1_label(program):
    """شكل class1 نفسه عند الطالب حتى يطابق فلتر الفرونت الصف/الشعبة."""
    cert = _CERT_AR.get(
        str(getattr(program, "certificate_type", "") or "").strip().lower(),
        str(getattr(program, "certificate_type", "") or "").strip(),
    )
    grade = (getattr(program, "grade", None) or "").strip()
    if cert and grade:
        return f"{cert} {grade}".strip()
    return cert or grade


def _normalize_certificate(value):
    text = str(value or "").strip()
    lowered = text.lower()
    if "بكالوريا" in text or lowered in ("baccalaureate", "bac"):
        return "baccalaureate"
    if "حادي عشر" in text or lowered in ("eleventh", "11"):
        return "eleventh"
    if lowered in ("transitional", "انتقالي", "تاسع", "عاشر"):
        return "transitional"
    return text


def _slot_lookup(data):
    return {
        "certificate_type": _normalize_certificate(data.get("certificate_type")),
        "grade": str(data.get("grade") or "").strip(),
        "section": str(data.get("section") or "").strip(),
        "day": _arabic_weekday(data.get("day")),
        "time_slot": _normalize_time_slot(data.get("time_slot")),
    }


def _slot_matches(program, lookup):
    return (
        _normalize_certificate(program.certificate_type) == lookup["certificate_type"]
        and (program.grade or "").strip() == lookup["grade"]
        and (program.section or "").strip() == lookup["section"]
        and _arabic_weekday(program.day) == lookup["day"]
        and _normalize_time_slot(program.time_slot) == lookup["time_slot"]
    )


def _existing_program_slot(validated_data):
    lookup = _slot_lookup(validated_data)
    if not lookup["day"] or not lookup["time_slot"]:
        return None
    for program in Program.objects.order_by("id"):
        if _slot_matches(program, lookup):
            return program
    return None


def programs_in_same_slot(instance):
    """كل الصفوف التي تمثل نفس خلية الجدول (الأحد 08:00 مثلاً)."""
    lookup = _slot_lookup(
        {
            "certificate_type": instance.certificate_type,
            "grade": instance.grade,
            "section": instance.section,
            "day": instance.day,
            "time_slot": instance.time_slot,
        }
    )
    return [
        program
        for program in Program.objects.all()
        if _slot_matches(program, lookup)
    ]


def _collapse_duplicate_slots(instance):
    for program in programs_in_same_slot(instance):
        if program.pk != instance.pk:
            program.delete()
