"""سجل حضور يومي مرتبط بطالب ومرحلة/شعبة اختيارياً."""
import uuid

from django.db import models

from academics.models import Student, Stage, Section


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
        unique_together = ("student", "Date")
        ordering = ("-Date",)

    def __str__(self):
        return f"{self.student} {self.Date} {self.Status}"
