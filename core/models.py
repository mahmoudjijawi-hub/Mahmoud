"""نماذج النواة: اشتراك المعهد البسيط (تاريخ انتهاء فقط)."""
from django.db import models


class Subscription(models.Model):
    """سجل اشتراك هذا المعهد — صف واحد عادة داخل قاعدة بيانات النشرة."""

    # تاريخ انتهاء عمل المعهد
    expiry_date = models.DateField(verbose_name="تاريخ الانتهاء")
    # إيقاف يدوي فوري دون تعديل التاريخ
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "اشتراك"
        verbose_name_plural = "الاشتراك"

    def __str__(self):
        # عرض مختصر في لوحة الإدارة
        return f"اشتراك حتى {self.expiry_date} — {'نشط' if self.is_active else 'موقوف'}"
