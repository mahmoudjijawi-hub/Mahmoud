"""مسلسل الامتحانات بأسماء الحقول كما في الـ Collection."""
from rest_framework import serializers

from academics.models import Student
from core.fields import FlexibleCharField
from grades.models import Exam


class ExamSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Student.objects.filter(is_active=True),
    )
    special_number = FlexibleCharField(max_length=10)
    Nameofexam = serializers.CharField(max_length=80)
    Subject_name = serializers.CharField(max_length=30)
    Date = serializers.DateField()
    Itsnote = serializers.CharField(max_length=80, required=False, allow_blank=True)
    Mark = serializers.IntegerField()
    Full_mark = serializers.IntegerField()

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

    def validate_special_number(self, value):
        if len(str(value)) > 10:
            raise serializers.ValidationError("الرقم المميز 10 خانات كحد أقصى.")
        return str(value)
