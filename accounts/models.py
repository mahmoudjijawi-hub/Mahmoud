"""نماذج المستخدم والمدير وسجل دخول المدير."""
import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from accounts.managers import CustomUserManager


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """مستخدم المنصة: مدير أو أستاذ أو طالب، بمفتاح UUID كما في توكن الـ Collection."""

    ROLE_MANAGER = "manager"
    ROLE_TEACHER = "teacher"
    ROLE_STUDENT = "student"
    ROLE_CHOICES = (
        (ROLE_MANAGER, "مدير"),
        (ROLE_TEACHER, "أستاذ"),
        (ROLE_STUDENT, "طالب"),
    )

    # مفتاح أساسي UUID ليطابق claim user_id في JWT داخل الـ Collection
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # اسم المستخدم — حد 25 حرفاً حسب متطلبات صفحة الدخول
    username = models.CharField(max_length=25, unique=True, verbose_name="اسم المستخدم")
    # الاسم الأول
    first_name = models.CharField(max_length=15, blank=True, verbose_name="الاسم الأول")
    # الكنية
    last_name = models.CharField(max_length=15, blank=True, verbose_name="الكنية")
    # الرقم المميز الفريد للتوجيه عند الدخول
    special_number = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="الرقم المميز",
    )
    # الدور النصي المستخدم في الصلاحيات
    role = models.CharField(
        max_length=16,
        choices=ROLE_CHOICES,
        default=ROLE_STUDENT,
        verbose_name="الدور",
    )
    # نوع المستخدم كما في الـ Collection: "1" مدير
    user_type = models.CharField(max_length=4, default="3", verbose_name="نوع المستخدم")
    # حساب نشط (يُستخدم أيضاً للشطب الناعم)
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    # صلاحية دخول Django Admin
    is_staff = models.BooleanField(default=False, verbose_name="طاقم")
    # تاريخ الإنشاء
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الانضمام")
    # مفتاح جلسة Django الأخيرة للمدير (جلسة واحدة)
    last_session_key = models.CharField(max_length=40, blank=True, default="")
    # آخر نشاط حقيقي — تُغلق الجلسة بعد ساعة خمول فقط
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="آخر نشاط")
    # إصدار JWT: زيادته تُبطل التوكنات القديمة لنفس المدير
    token_version = models.PositiveIntegerField(default=0)

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["special_number"]

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"

    def __str__(self):
        return self.username

    def bump_token_version(self):
        """زيادة إصدار التوكن لإبطال الوصول السابق لهذا الحساب."""
        self.token_version = models.F("token_version") + 1
        self.save(update_fields=["token_version"])
        self.refresh_from_db(fields=["token_version"])


class Manager(models.Model):
    """ملف المدير كموارد /api/managers/ بمفتاح UUID مستقل عن المستخدم."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # ربط واحد لواحد مع حساب الدخول
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="manager_profile",
        verbose_name="المستخدم",
    )
    first_name = models.CharField(max_length=15, verbose_name="الاسم الأول")
    last_name = models.CharField(max_length=15, verbose_name="الكنية")
    special_number = models.CharField(max_length=7, unique=True, verbose_name="الرقم المميز")
    user_type = models.CharField(max_length=4, default="1", verbose_name="نوع المستخدم")

    class Meta:
        verbose_name = "مدير"
        verbose_name_plural = "المديرون"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class LoginLog(models.Model):
    """سجل كل دخول ناجح للمدير (تدقيق أمني)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="login_logs",
        verbose_name="المستخدم",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="التاريخ والوقت")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="عنوان IP")
    user_agent = models.TextField(blank=True, default="", verbose_name="المتصفح/الجهاز")

    class Meta:
        verbose_name = "سجل دخول"
        verbose_name_plural = "سجلات الدخول"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user.username} @ {self.created_at}"


class ManagerLoginGuard(models.Model):
    """عدّاد محاولات صفحة اسم المدير وكلمة المرور — مشترك بين كل عمال Render."""

    ident = models.CharField(max_length=190, primary_key=True)
    attempts = models.JSONField(default=list, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "قفل دخول المدير"
        verbose_name_plural = "أقفال دخول المدير"

    def __str__(self):
        return self.ident
