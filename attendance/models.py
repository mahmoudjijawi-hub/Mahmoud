"""سجل حضور يومي مرتبط بطالب ومرحلة/شعبة اختيارياً."""
import uuid

from django.db import models

from academics.models import Student, Stage, Section


_SUBJECT_AR = {
    "math": "رياضيات",
    "mathematics": "رياضيات",
    "science": "علوم",
    "physics": "فيزياء",
    "chemistry": "كيمياء",
    "arabic": "عربي",
    "national": "وطنية",
    "religion": "ديانة",
    "english": "انكليزي",
    "french": "فرنسي",
    "geography": "جغرافيا",
    "history": "تاريخ",
    "philosophy": "فلسفة",
}


def attendance_subject_key(value):
    """توحيد اسم المادة حتى math ورياضيات يبقيا نفس السجل."""
    text = str(value or "").strip()
    if not text:
        return ""
    return _SUBJECT_AR.get(text.lower(), text)[:30]


class Attendance(models.Model):
    STATUS_PRESENT = "حضور"
    STATUS_ABSENT = "غياب"
    STATUS_CHOICES = (
        (STATUS_PRESENT, "حضور"),
        (STATUS_ABSENT, "غياب"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="attendances",
        verbose_name="الطالب",
    )
    Date = models.DateField(verbose_name="التاريخ")
    subject = models.CharField(max_length=30, blank=True, default="", verbose_name="المادة")
    Status = models.CharField(max_length=10, choices=STATUS_CHOICES, verbose_name="الحالة")
    stage = models.ForeignKey(
        Stage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="المرحلة",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="الشعبة",
    )

    class Meta:
        verbose_name = "حضور"
        verbose_name_plural = "الحضور"
        unique_together = ("student", "Date", "subject")
        ordering = ("-Date", "subject")

    def __str__(self):
        return f"{self.student} {self.Date} {self.subject} {self.Status}"
