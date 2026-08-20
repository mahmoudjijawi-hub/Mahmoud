"""مسلسلات time_table و programs بأسماء حقول الـ Collection."""
from rest_framework import serializers

from academics.models import Student, Teacher
from schedule.models import TimeTable, Program


class TimeTableSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Student.objects.filter(is_active=True),
    )
    Day = serializers.DateField()
    Hour = serializers.TimeField()
    Subject = serializers.CharField(max_length=30)
    Teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all())

    class Meta:
        model = TimeTable
        fields = ("id", "student", "Day", "Hour", "Subject", "Teacher")
        read_only_fields = ("id",)


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
