"""نماذج المراحل والمواد والشعب والأستاذ والطالب."""
import uuid

from django.conf import settings
from django.db import models

from academics.files import UUIDCVUploadTo, validate_cv_file


class Stage(models.Model):
    """مرحلة دراسية قابلة للإدارة (بكالوريا، حادي عشر...)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True, verbose_name="اسم المرحلة")

    class Meta:
        verbose_name = "مرحلة"
        verbose_name_plural = "المراحل"

    def __str__(self):
        return self.name


class Subject(models.Model):
    """مادة دراسية قابلة للإدارة."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=30, unique=True, verbose_name="اسم المادة")

    class Meta:
        verbose_name = "مادة"
        verbose_name_plural = "المواد"

    def __str__(self):
        return self.name


class Section(models.Model):
    """شعبة مرتبطة بمرحلة."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, verbose_name="اسم الشعبة")
    stage = models.ForeignKey(
        Stage,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name="المرحلة",
    )

    class Meta:
        verbose_name = "شعبة"
        verbose_name_plural = "الشعب"
        unique_together = ("name", "stage")

    def __str__(self):
        return f"{self.stage} — {self.name}"


class Teacher(models.Model):
    """أستاذ — حقول POST/PATCH /api/teachers/ حرفياً كما في الـ Collection."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        verbose_name="المستخدم",
    )
    first_name = models.CharField(max_length=15, verbose_name="الاسم الأول")
    last_name = models.CharField(max_length=15, verbose_name="الكنية")
    special_number = models.CharField(max_length=10, unique=True, verbose_name="الرقم المميز")
    # يُخزَّن كنص لاستيعاب true و Yes من الـ Collection
    gender = models.CharField(max_length=10, blank=True, default="", verbose_name="الجنس")
    teacher_number = models.CharField(max_length=10, verbose_name="رقم الهاتف")
    expertise = models.CharField(max_length=30, verbose_name="المادة/الخبرة")
    # نص السيرة كما في جسم الـ Collection
    cv = models.CharField(max_length=175, blank=True, default="", verbose_name="السيرة")
    # ملف مرفوع اختياري غير إلزامي في الـ Serializer
    cv_file = models.FileField(
        upload_to=UUIDCVUploadTo(),
        blank=True,
        null=True,
        validators=[validate_cv_file],
        verbose_name="ملف السيرة",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teachers",
        verbose_name="المادة",
    )

    class Meta:
        verbose_name = "أستاذ"
        verbose_name_plural = "الأساتذة"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Student(models.Model):
    """طالب — حقول /api/students/ حرفياً كما في الـ Collection."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
        verbose_name="المستخدم",
    )
    first_name = models.CharField(max_length=15, verbose_name="الاسم الأول")
    last_name = models.CharField(max_length=15, verbose_name="الكنية")
    special_number = models.CharField(max_length=10, unique=True, verbose_name="الرقم المميز")
    student_class = models.CharField(max_length=20, verbose_name="الصف/المرحلة")
    parent_number = models.CharField(max_length=10, verbose_name="هاتف الأهل")
    student_number = models.CharField(max_length=10, verbose_name="هاتف الطالب")
    address = models.CharField(max_length=100, verbose_name="عنوان السكن")
    personal_notes = models.CharField(max_length=100, blank=True, default="", verbose_name="ملاحظات")
    is_payer = models.BooleanField(default=False, verbose_name="مسدد")
    class1 = models.CharField(max_length=30, blank=True, default="", verbose_name="مادة 1")
    class2 = models.CharField(max_length=30, blank=True, default="", verbose_name="مادة 2")
    class3 = models.CharField(max_length=30, blank=True, default="", verbose_name="مادة 3")
    stage = models.ForeignKey(
        Stage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        verbose_name="المرحلة",
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
        verbose_name="الشعبة",
    )
    # شطب ناعم للحفاظ على السجلات التاريخية
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
