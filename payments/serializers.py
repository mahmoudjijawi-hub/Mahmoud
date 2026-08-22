"""مسلسل الدفعات بأسماء الحقول كما في الـ Collection مع دعم زر الدفعة الكاملة."""
import uuid
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


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _resolve_student(value):
    """
    يقبل:
    - UUID
    - رقم مميز كنص/رقم
    - كائن {id} أو {special_number}
    """
    if value is None or value == "":
        return None
    if isinstance(value, Student):
        return value
    if isinstance(value, dict):
        if value.get("id"):
            return Student.objects.filter(pk=value["id"]).first()
        special = (
            value.get("special_number")
            or value.get("specialNumber")
            or value.get("number")
        )
        if special is not None and str(special).strip() != "":
            from core.digits import normalize_digits

            return Student.objects.filter(
                special_number=normalize_digits(str(special).strip())
            ).first()
        return None

    text = str(value).strip()
    if not text:
        return None
    from core.digits import normalize_digits

    text = normalize_digits(text)
    if _is_uuid(text):
        return Student.objects.filter(pk=text).first()
    # الفرونت غالباً يضع الرقم المميز في حقل student
    return Student.objects.filter(special_number=text).first()


class FlexibleStudentField(serializers.Field):
    """حقل طالب يقبل UUID أو رقماً مميزاً أو كائناً متداخلاً."""

    def to_internal_value(self, data):
        student = _resolve_student(data)
        if student is None:
            raise serializers.ValidationError("الطالب غير موجود أو غير نشط.")
        return student

    def to_representation(self, value):
        return str(value.pk) if value is not None else None


class PaymentSerializer(serializers.ModelSerializer):
    student = FlexibleStudentField(required=False)
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
        if hasattr(data, "items"):
            data = {k: v for k, v in data.items()}
        else:
            data = dict(data or {})

        # الفرونت غالباً يرسل "" بدل حذف الحقل — DecimalField يرفض النص الفارغ
        for money_key in (
            "FullAmount",
            "PaidAmount",
            "Paymentresult",
            "full_amount",
            "paid_amount",
            "payment_result",
            "fullAmount",
            "paidAmount",
            "paymentResult",
            "amount",
            "paid",
            "total",
            "remaining",
        ):
            if money_key in data and isinstance(data.get(money_key), str) and data.get(money_key).strip() == "":
                data[money_key] = None

        if "FullAmount" not in data or data.get("FullAmount") in (None, ""):
            alias = _pick(data, "full_amount", "fullAmount", "amount", "total", "Fullamount")
            if alias is not None:
                data["FullAmount"] = alias
        if "PaidAmount" not in data or data.get("PaidAmount") in (None, ""):
            alias = _pick(data, "paid_amount", "paidAmount", "paid", "Paidamount")
            if alias is not None:
                data["PaidAmount"] = alias
        # إن بقي PaidAmount فارغاً نحذفه ليُحسب كدفعة كاملة في validate()
        if data.get("PaidAmount") in (None, ""):
            data.pop("PaidAmount", None)
        if "Paymentresult" not in data or data.get("Paymentresult") in (None, ""):
            alias = _pick(data, "payment_result", "paymentResult", "remaining", "PaymentResult")
            if alias is not None:
                data["Paymentresult"] = alias
        if data.get("Paymentresult") in (None, ""):
            data.pop("Paymentresult", None)
        if "payment_type" not in data or data.get("payment_type") in (None, ""):
            alias = _pick(data, "paymentType", "type", "mode")
            if alias is not None:
                data["payment_type"] = alias
        if "special_number" not in data or data.get("special_number") in (None, ""):
            alias = _pick(data, "specialNumber", "number", "student_special_number")
            if alias is not None:
                data["special_number"] = alias
        if "student" not in data or data.get("student") in (None, ""):
            alias = _pick(data, "student_id", "studentId", "studentUUID")
            if alias is not None:
                data["student"] = alias
        if data.get("student") in (None, ""):
            data.pop("student", None)

        return super().to_internal_value(data)

    def validate(self, attrs):
        raw = getattr(self, "initial_data", {}) or {}
        special = str(
            attrs.pop("special_number", None)
            or _pick(raw, "special_number", "specialNumber", "number")
            or ""
        ).strip()

        student = attrs.get("student")
        if student is None and special:
            student = _resolve_student(special)
            if student is None:
                raise serializers.ValidationError(
                    {"student": "لا يوجد طالب نشط بهذا الرقم المميز."}
                )
            attrs["student"] = student
        if attrs.get("student") is None and self.instance is None:
            # محاولة أخيرة من الحقل student الخام
            student = _resolve_student(_pick(raw, "student", "student_id", "studentId"))
            if student is not None:
                attrs["student"] = student
        if attrs.get("student") is None and self.instance is None:
            raise serializers.ValidationError(
                {"student": "يجب تحديد الطالب أو الرقم المميز."}
            )

        full_amount = attrs.get("FullAmount")
        paid_amount = attrs.get("PaidAmount")
        payment_type = str(
            attrs.get("payment_type")
            or _pick(raw, "payment_type", "paymentType", "type")
            or ""
        ).strip().lower()

        is_full_flag = str(
            _pick(raw, "is_full", "fullPayment", "pay_full", "full") or ""
        ).lower() in ("1", "true", "yes", "full")
        is_full = is_full_flag or payment_type in (
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

        # زر دفعة كاملة: إذا لم يُرسل PaidAmount نعتبره = FullAmount دائماً
        if paid_amount is None:
            if is_full or self.instance is None:
                # إنشاء جديد بدون PaidAmount = دفعة كاملة (سلوك زر الواجهة)
                paid_amount = full_amount
                attrs["payment_type"] = Payment.TYPE_FULL
                is_full = True
            else:
                paid_amount = self.instance.PaidAmount
        else:
            paid_amount = _to_decimal(paid_amount, "PaidAmount")

        if is_full:
            paid_amount = full_amount
            attrs["payment_type"] = Payment.TYPE_FULL

        if paid_amount > full_amount:
            raise serializers.ValidationError(
                "المبلغ المدفوع لا يجوز أن يتجاوز القسط الكلي."
            )

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
        if payment.Paymentresult <= 0 and not student.is_payer:
            student.is_payer = True
            student.save(update_fields=["is_payer"])

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

    def to_representation(self, instance):
        """استجابة غنية يفهمها الفرونت بعد الضغط على زر الدفع."""
        data = super().to_representation(instance)
        data["success"] = True
        data["message"] = "تمت عملية الدفع بنجاح"
        data["detail"] = "تمت عملية الدفع بنجاح"
        # مرادفات snake_case / camelCase شائعة في الواجهات
        data["full_amount"] = data.get("FullAmount")
        data["paid_amount"] = data.get("PaidAmount")
        data["payment_result"] = data.get("Paymentresult")
        data["fullAmount"] = data.get("FullAmount")
        data["paidAmount"] = data.get("PaidAmount")
        data["paymentResult"] = data.get("Paymentresult")
        data["student_id"] = data.get("student")
        if instance.student_id:
            student = instance.student
            # بيانات الطالب داخل الدفعة حتى تملأ الواجهة بقية الحقول
            # بمجرد إدخال الرقم المميز دون طلب إضافي.
            data["special_number"] = student.special_number
            data["specialNumber"] = student.special_number
            data["is_payer"] = student.is_payer
            data["isPayer"] = student.is_payer
            data["first_name"] = student.first_name
            data["last_name"] = student.last_name
            data["student_name"] = f"{student.first_name} {student.last_name}".strip()
            data["studentName"] = data["student_name"]
            data["student_class"] = student.student_class
            data["studentClass"] = student.student_class
            data["parent_number"] = student.parent_number
            data["student_number"] = student.student_number
            data["student_details"] = {
                "id": str(student.id),
                "first_name": student.first_name,
                "last_name": student.last_name,
                "special_number": student.special_number,
                "student_class": student.student_class,
                "parent_number": student.parent_number,
                "student_number": student.student_number,
                "address": student.address,
                "is_payer": student.is_payer,
            }
        return data
