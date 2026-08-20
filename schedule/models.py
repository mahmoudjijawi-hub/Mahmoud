"""الجدول الزمني (time_table) والبرنامج (programs) بحقول الـ Collection."""
import uuid

from django.db import models

from academics.models import Student, Teacher


class TimeTable(models.Model):
    """حصة مرتبطة بطلاب وتاريخ وساعة كما في /api/time_table/."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ManyToManyField(Student, related_name="time_tables", verbose_name="الطلاب")
    Day = models.DateField(verbose_name="اليوم")
    Hour = models.TimeField(verbose_name="الساعة")
    Subject = models.CharField(max_length=30, verbose_name="المادة")
    Teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="time_tables",
        verbose_name="الأستاذ",
    )

    class Meta:
        verbose_name = "حصة زمنية"
        verbose_name_plural = "الجدول الزمني"
        ordering = ("Day", "Hour")

    def __str__(self):
        return f"{self.Subject} {self.Day} {self.Hour}"


class Program(models.Model):
    """برنامج دراسي أسبوعي كما في جسم طلب program بالـ Collection."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    certificate_type = models.CharField(max_length=40, verbose_name="نوع الشهادة")
    grade = models.CharField(max_length=30, verbose_name="الصف")
    section = models.CharField(max_length=40, verbose_name="الشعبة")
    day = models.CharField(max_length=20, verbose_name="اليوم")
    time_slot = models.CharField(max_length=20, verbose_name="الحصة")
    room = models.CharField(max_length=40, verbose_name="القاعة")
    subject_name = models.CharField(max_length=30, verbose_name="المادة")
    teacher_name = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="programs",
        verbose_name="الأستاذ",
    )

    class Meta:
        verbose_name = "برنامج"
        verbose_name_plural = "البرامج"

    def __str__(self):
        return f"{self.day} {self.time_slot} {self.subject_name}"
