"""نموذج المذاكرة/الامتحان بحقول الـ Collection حرفياً."""
import uuid

from django.db import models

from academics.models import Student


class Exam(models.Model):
    """سجل مذاكرة مرتبط بعدة طلاب كما في جسم POST exams."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ManyToManyField(Student, related_name="exams", verbose_name="الطلاب")
    special_number = models.CharField(max_length=10, verbose_name="الرقم المميز")
    Nameofexam = models.CharField(max_length=80, verbose_name="اسم المذاكرة")
    Subject_name = models.CharField(max_length=30, verbose_name="المادة")
    Date = models.DateField(verbose_name="تاريخ التقديم")
    Itsnote = models.CharField(max_length=80, blank=True, default="", verbose_name="ملاحظة")
    Mark = models.IntegerField(verbose_name="العلامة")
    Full_mark = models.IntegerField(verbose_name="العلامة الكاملة")

    class Meta:
        verbose_name = "مذاكرة"
        verbose_name_plural = "المذاكرات"
        ordering = ("-Date",)

    def __str__(self):
        return self.Nameofexam
