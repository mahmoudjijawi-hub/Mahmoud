"""مسلسل الدفعات بأسماء الحقول كما في الـ Collection مع دعم دفعة كاملة من الفرونت."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers

from academics.models import Student
from payments.models import Payment, PaymentTransaction


def _to_decimal(value, field_name):
    """تحويل مرن للمبالغ القادمة كنص/رقم من الواجهة."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise serializers.ValidationError({field_name: "قيمة المبلغ غير صالحة."}) from exc


def _pick(data, *keys):
    """اختيار أول قيمة غير فارغة من مفاتيح محتملة يرسلها الفرونت."""
    if not isinstance(data, dict):
        return None
    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
        value = lowered.get(str(key).lower())
        if value not in (None, ""):
            return value
    return None


class PaymentSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    FullAmount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    PaidAmount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    Paymentresult = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    payment_type = serializers.CharField(required=False, allow_blank=True)
    special_number = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "student",
            "FullAmount",
            "PaidAmount",
            "Paymentresult",
            "payment_type",
            "status",
            "special_number",
        )
        read_only_fields = ("id", "status")

    def to_internal_value(self, data):
        # تطبيع أسماء الحقول الشائعة من الفرونت قبل التحقق
        if hasattr(data, "copy"):
            data = data.copy()
        else:
            data = dict(data or {})

        if "FullAmount" not in data:
            alias = _pick(data, "full_amount", "fullAmount", "amount", "total", "Fullamount")
            if alias is not None:
                data["FullAmount"] = alias
        if "PaidAmount" not in data:
            alias = _pick(data, "paid_amount", "paidAmount", "paid", "Paidamount")
            if alias is not None:
                data["PaidAmount"] = alias
        if "Paymentresult" not in data:
            alias = _pick(data, "payment_result", "paymentResult", "remaining", "PaymentResult")
            if alias is not None:
                data["Paymentresult"] = alias
        if "payment_type" not in data:
            alias = _pick(data, "paymentType", "type", "mode")
            if alias is not None:
                data["payment_type"] = alias
        if "special_number" not in data:
            alias = _pick(data, "specialNumber", "number", "student_special_number")
            if alias is not None:
                data["special_number"] = alias
        if "student" not in data or data.get("student") in (None, ""):
            alias = _pick(data, "student_id", "studentId", "studentUUID")
            if alias is not None:
                data["student"] = alias

        return super().to_internal_value(data)

    def validate(self, attrs):
        raw = getattr(self, "initial_data", {}) or {}
        special = str(attrs.pop("special_number", None) or _pick(raw, "special_number", "specialNumber") or "").strip()

        student = attrs.get("student")
        if student is None and special:
            student = Student.objects.filter(special_number=special, is_active=True).first()
            if student is None:
                raise serializers.ValidationError({"student": "لا يوجد طالب نشط بهذا الرقم المميز."})
            attrs["student"] = student
        if attrs.get("student") is None and self.instance is None:
            raise serializers.ValidationError({"student": "يجب تحديد الطالب أو الرقم المميز."})

        full_amount = attrs.get("FullAmount")
        paid_amount = attrs.get("PaidAmount")
        payment_type = str(attrs.get("payment_type") or _pick(raw, "payment_type", "paymentType", "type") or "").strip().lower()

        # زر «دفعة كاملة»: إن لم يُرسل المدفوع نعتبره مساوياً للقسط الكلي
        is_full = payment_type in (
            "full",
            "full_payment",
            "fullpayment",
            "complete",
            "كامل",
            "كاملة",
            "دفعة كاملة",
            "دفع كاملة",
        )
        if full_amount is None and self.instance is not None:
            full_amount = self.instance.FullAmount
        if full_amount is None:
            raise serializers.ValidationError({"FullAmount": "القسط الكلي مطلوب."})

        full_amount = _to_decimal(full_amount, "FullAmount")
        attrs["FullAmount"] = full_amount

        if paid_amount is None:
            if is_full or str(_pick(raw, "is_full", "fullPayment", "pay_full") or "").lower() in (
                "1",
                "true",
                "yes",
            ):
                paid_amount = full_amount
                attrs["payment_type"] = Payment.TYPE_FULL
            elif self.instance is not None:
                paid_amount = self.instance.PaidAmount
            else:
                raise serializers.ValidationError({"PaidAmount": "المبلغ المدفوع مطلوب."})
        else:
            paid_amount = _to_decimal(paid_amount, "PaidAmount")

        # دفعة كاملة صريحة: المدفوع = الكلي والمتبقي = 0
        if is_full:
            paid_amount = full_amount
            attrs["payment_type"] = Payment.TYPE_FULL

        if paid_amount > full_amount:
            raise serializers.ValidationError("المبلغ المدفوع لا يجوز أن يتجاوز القسط الكلي.")

        attrs["PaidAmount"] = paid_amount
        attrs["Paymentresult"] = full_amount - paid_amount
        if attrs["Paymentresult"] <= 0:
            attrs["payment_type"] = Payment.TYPE_FULL
        elif not attrs.get("payment_type"):
            attrs["payment_type"] = Payment.TYPE_INSTALLMENT
        return attrs

    def _sync_student_payer(self, payment):
        """تحديث حالة is_payer للطالب عند اكتمال الدفع."""
        student = payment.student
        if payment.Paymentresult <= 0:
            if not student.is_payer:
                student.is_payer = True
                student.save(update_fields=["is_payer"])
        elif student.is_payer and payment.Paymentresult > 0:
            # إن بقي متبقي نُبقي العلم كما هو إلا إذا لم تعد هناك دفعات مكتملة
            pass

    def _apply_amounts(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.recalculate()
        instance.save()
        self._sync_student_payer(instance)
        return instance

    @transaction.atomic
    def create(self, validated_data):
        payment = Payment(
            student=validated_data["student"],
            FullAmount=validated_data["FullAmount"],
            PaidAmount=validated_data["PaidAmount"],
            Paymentresult=validated_data.get("Paymentresult") or Decimal("0"),
            payment_type=validated_data.get("payment_type") or Payment.TYPE_FULL,
        )
        payment.recalculate()
        payment.save()
        self._sync_student_payer(payment)
        PaymentTransaction.objects.create(
            payment=payment,
            amount=payment.PaidAmount,
            note="دفعة كاملة" if payment.payment_type == Payment.TYPE_FULL else "إنشاء دفعة",
        )
        return payment

    @transaction.atomic
    def update(self, instance, validated_data):
        old_paid = instance.PaidAmount
        instance = self._apply_amounts(instance, validated_data)
        delta = instance.PaidAmount - old_paid
        PaymentTransaction.objects.create(
            payment=instance,
            amount=delta,
            note="دفعة كاملة" if instance.payment_type == Payment.TYPE_FULL else "تعديل دفعة",
        )
        return instance
