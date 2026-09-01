"""نماذج الدفع وحركة التدقيق."""
import uuid
from decimal import Decimal

from django.db import models

from academics.models import Student


class Payment(models.Model):
    """دفعة طالب بحقول FullAmount و PaidAmount و Paymentresult كما في الـ Collection."""

    STATUS_PENDING = "قيد التحصيل"
    STATUS_COMPLETE = "مكتمل"
    TYPE_FULL = "full"
    TYPE_INSTALLMENT = "installment"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="الطالب",
    )
    FullAmount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="القسط الكلي")
    PaidAmount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المدفوع")
    Paymentresult = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="المتبقي")
    payment_type = models.CharField(max_length=20, default=TYPE_FULL, verbose_name="نوع الدفع")
    status = models.CharField(max_length=20, default=STATUS_PENDING, verbose_name="حالة الحساب")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ العملية")

    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "المدفوعات"
        ordering = ("-created_at",)

    def recalculate(self):
        """حساب المتبقي والحالة من المبالغ دون SQL خام."""
        remaining = (self.FullAmount or Decimal("0")) - (self.PaidAmount or Decimal("0"))
        self.Paymentresult = remaining
        if remaining <= 0:
            self.status = self.STATUS_COMPLETE
            self.payment_type = self.TYPE_FULL if self.PaidAmount == self.FullAmount else self.payment_type
        else:
            self.status = self.STATUS_PENDING
            if self.PaidAmount and self.PaidAmount < self.FullAmount:
                self.payment_type = self.TYPE_INSTALLMENT

    def __str__(self):
        return f"{self.student} {self.PaidAmount}/{self.FullAmount}"


class PaymentTransaction(models.Model):
    """حركة مالية منفصلة لكل إضافة/تعديل دفعة لأغراض التدقيق."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name="الدفعة",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="القيمة")
    note = models.CharField(max_length=80, blank=True, default="", verbose_name="ملاحظة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="التاريخ")

    class Meta:
        verbose_name = "حركة مالية"
        verbose_name_plural = "الحركات المالية"
        ordering = ("-created_at",)
