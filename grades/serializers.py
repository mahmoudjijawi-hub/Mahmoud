"""مسلسل الامتحانات: أسماء الـ Collection + أسماء شاشة العلامات في الواجهة."""
from rest_framework import serializers

from academics.models import Student
from core.fields import FlexibleCharField
from grades.models import Exam


class FlexibleScoreField(serializers.IntegerField):
    """يقبل 90 أو \"90\" أو 90.0 كما ترسل الواجهة."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
            if data == "":
                self.fail("invalid")
            try:
                data = float(data)
            except (TypeError, ValueError):
                self.fail("invalid")
        if isinstance(data, float):
            data = int(round(data))
        return super().to_internal_value(data)


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


class ExamSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Student.objects.all(),
        required=False,
    )
    special_number = FlexibleCharField(max_length=10, required=False, allow_blank=True)
    Nameofexam = serializers.CharField(max_length=80)
    Subject_name = serializers.CharField(max_length=30)
    Date = serializers.DateField()
    Itsnote = serializers.CharField(max_length=80, required=False, allow_blank=True)
    Mark = FlexibleScoreField()
    Full_mark = FlexibleScoreField()

    class Meta:
        model = Exam
        fields = (
            "id",
            "student",
            "special_number",
            "Nameofexam",
            "Subject_name",
            "Date",
            "Itsnote",
            "Mark",
            "Full_mark",
        )
        read_only_fields = ("id",)

    def to_internal_value(self, data):
        if hasattr(data, "items"):
            data = {k: v for k, v in data.items()}
        else:
            data = dict(data or {})

        name = _first(data, "Nameofexam", "nameofexam", "nameOfExam", "exam_name", "examName", "name")
        if name is not None:
            data["Nameofexam"] = name
        subject = _first(
            data, "Subject_name", "subject_name", "subjectName", "Subject", "subject"
        )
        if subject is not None:
            data["Subject_name"] = subject
        date = _first(data, "Date", "date", "examDate", "exam_date")
        if date is not None:
            data["Date"] = date
        note = _first(data, "Itsnote", "itsnote", "itsNote", "note", "studentNote")
        if note is not None:
            data["Itsnote"] = note
        mark = _first(data, "Mark", "mark", "score")
        if mark is not None:
            data["Mark"] = mark
        full = _first(data, "Full_mark", "full_mark", "fullMark", "fullmark")
        if full is not None:
            data["Full_mark"] = full

        student = _first(data, "student", "students", "student_id", "studentId")
        if student is not None and not isinstance(student, (list, tuple)):
            data["student"] = [student]
        elif isinstance(student, (list, tuple)):
            data["student"] = list(student)

        return super().to_internal_value(data)

    def validate_special_number(self, value):
        if value in (None, ""):
            return ""
        if len(str(value)) > 10:
            raise serializers.ValidationError("الرقم المميز 10 خانات كحد أقصى.")
        return str(value)

    def validate(self, attrs):
        students = attrs.get("student") or []
        if not students:
            raise serializers.ValidationError({"student": "يجب تحديد الطالب."})
        if not attrs.get("special_number"):
            attrs["special_number"] = students[0].special_number
        mark = attrs.get("Mark")
        full = attrs.get("Full_mark")
        if mark is not None and full is not None and mark > full:
            raise serializers.ValidationError({"Mark": "العلامة لا يجوز أن تتجاوز العلامة الكلية."})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["nameofexam"] = data.get("Nameofexam")
        data["subject_name"] = data.get("Subject_name")
        data["date"] = data.get("Date")
        data["itsnote"] = data.get("Itsnote")
        data["mark"] = data.get("Mark")
        data["full_mark"] = data.get("Full_mark")
        return data
