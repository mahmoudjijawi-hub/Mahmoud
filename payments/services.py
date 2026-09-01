"""خدمة دفع موحّدة لزر الدفع — إنشاء أو إكمال دفعة كاملة."""
import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from payments.models import Payment, PaymentTransaction
from payments.serializers import PaymentSerializer, _resolve_student, _pick, _to_decimal


def extract_raw_payload(request):
    """استخراج الجسم من data أو query أو raw body."""
    payload = {}
    data = getattr(request, "data", None)
    if data is not None and hasattr(data, "items"):
        payload.update({k: v for k, v in data.items()})
    elif isinstance(data, dict):
        payload.update(data)

    query = getattr(request, "query_params", None)
    if query is not None:
        for key, value in query.items():
            if key not in payload or payload.get(key) in (None, ""):
                payload[key] = value

    # Content-Type خاطئ → request.data فارغ؛ نقرأ JSON من الجسم مباشرة
    if not any(v not in (None, "") for v in payload.values()):
        try:
            raw = request.body.decode("utf-8") if getattr(request, "body", None) else ""
            if raw.strip():
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    payload = parsed
        except Exception:
            pass
    return payload


def _money(payload, *keys):
    raw = _pick(payload, *keys)
    if raw in (None, ""):
        return None
    try:
        return _to_decimal(raw, keys[0])
    except ValidationError:
        return None


def _student_paid_total(student):
    """مجموع PaidAmount لكل صفوف الطالب (شاشة الأقساط تجمع هذه القيم)."""
    return Payment.objects.filter(student=student).aggregate(
        total=Sum("PaidAmount")
    )["total"] or Decimal("0.00")


def _append_installment(student, full_amount, paid_amount):
    """
    شاشة الأقساط ترسل PaidAmount = مبلغ هذه الدفعة فقط.
    كل POST ينشئ صفاً جديداً ولا يستبدل المدفوع السابق.
    """
    existing_paid = _student_paid_total(student)
    remaining_after = full_amount - existing_paid - paid_amount
    if remaining_after < 0:
        max_now = full_amount - existing_paid
        raise ValidationError(
            {
                "PaidAmount": (
                    "المبلغ المدفوع يتجاوز المتبقي. "
                    f"الحد الأقصى المسموح دفعه الآن هو: {max_now}"
                ),
                "detail": (
                    "المبلغ المدفوع يتجاوز المتبقي. "
                    f"الحد الأقصى المسموح دفعه الآن هو: {max_now}"
                ),
            }
        )
    payment = Payment(
        student=student,
        FullAmount=full_amount,
        PaidAmount=paid_amount,
        Paymentresult=remaining_after,
        payment_type=(
            Payment.TYPE_FULL if remaining_after <= 0 else Payment.TYPE_INSTALLMENT
        ),
        status=(
            Payment.STATUS_COMPLETE if remaining_after <= 0 else Payment.STATUS_PENDING
        ),
    )
    payment.save()
    PaymentTransaction.objects.create(
        payment=payment,
        amount=paid_amount,
        note="قسط",
    )
    if remaining_after <= 0 and not student.is_payer:
        student.is_payer = True
        student.save(update_fields=["is_payer"])
    return payment, PaymentSerializer(payment).data


def _update_full_amount_only(student, full_amount):
    """تغيير القسط الكلي دون دفعة جديدة — لا تُصفَّر PaidAmount السابقة."""
    latest = (
        Payment.objects.select_for_update()
        .filter(student=student)
        .order_by("-created_at")
        .first()
    )
    total_paid = _student_paid_total(student)
    remaining = full_amount - total_paid
    if remaining < 0:
        raise ValidationError(
            {
                "FullAmount": "القسط الكلي أصغر من مجموع المدفوع.",
                "detail": "القسط الكلي أصغر من مجموع المدفوع.",
            }
        )
    if latest is None:
        payment = Payment(
            student=student,
            FullAmount=full_amount,
            PaidAmount=Decimal("0.00"),
            Paymentresult=full_amount,
            payment_type=Payment.TYPE_INSTALLMENT,
            status=Payment.STATUS_PENDING,
        )
        payment.save()
        PaymentTransaction.objects.create(
            payment=payment,
            amount=Decimal("0.00"),
            note="تحديد القسط الكلي",
        )
        return payment, PaymentSerializer(payment).data

    latest.FullAmount = full_amount
    latest.Paymentresult = remaining
    latest.status = (
        Payment.STATUS_COMPLETE if remaining <= 0 else Payment.STATUS_PENDING
    )
    if remaining <= 0:
        latest.payment_type = Payment.TYPE_FULL
        if not student.is_payer:
            student.is_payer = True
            student.save(update_fields=["is_payer"])
    else:
        latest.payment_type = Payment.TYPE_INSTALLMENT
    latest.save()
    return latest, PaymentSerializer(latest).data


@transaction.atomic
def execute_payment(payload, force_full=False):
    """
    تنفيذ دفع مرن يُرجع (payment, response_dict).
    - شاشة الأقساط: كل قسط صف جديد (PaidAmount = الزيادة هذه المرة)
    - زر الدفعة الكاملة (force_full): يكمل القسط المفتوح في مكانه
    """
    payload = dict(payload or {})
    if force_full:
        payload["payment_type"] = Payment.TYPE_FULL

    student = _resolve_student(
        _pick(payload, "student", "student_id", "studentId")
        or _pick(payload, "special_number", "specialNumber", "number")
    )

    full_amount = _money(
        payload, "FullAmount", "full_amount", "fullAmount", "amount", "total", "Fullamount"
    )
    paid_amount = _money(
        payload, "PaidAmount", "paid_amount", "paidAmount", "paid", "Paidamount"
    )
    if full_amount is None and paid_amount is not None:
        full_amount = paid_amount
    if paid_amount is None and full_amount is not None:
        paid_amount = full_amount

    if student is None:
        # اترك المسلسل يُظهر خطأ الطالب بوضوح
        data = {**payload}
        if full_amount is not None:
            data["FullAmount"] = str(full_amount)
        if paid_amount is not None:
            data["PaidAmount"] = str(paid_amount)
        if force_full:
            data["payment_type"] = Payment.TYPE_FULL
        serializer = PaymentSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return payment, PaymentSerializer(payment).data

    # شاشة الأقساط (InstallmentManager): PaidAmount دفعة جزئية تُضاف كسجل مستقل.
    if (
        not force_full
        and full_amount is not None
        and paid_amount is not None
        and paid_amount > Decimal("0.00")
        and paid_amount < full_amount
    ):
        return _append_installment(student, full_amount, paid_amount)

    # تحديث القسط الكلي فقط (PaidAmount = 0) دون مسح المدفوع السابق.
    if (
        not force_full
        and full_amount is not None
        and paid_amount == Decimal("0.00")
    ):
        return _update_full_amount_only(student, full_amount)

    open_payment = (
        Payment.objects.select_for_update()
        .filter(student=student)
        .exclude(Paymentresult=0)
        .order_by("-created_at")
        .first()
    )

    # حدّث القسط المفتوح بدل إنشاء سجل مكرر
    if open_payment is not None:
        old_paid = open_payment.PaidAmount
        if full_amount is not None:
            open_payment.FullAmount = full_amount
        if force_full or paid_amount is None:
            open_payment.PaidAmount = open_payment.FullAmount
            open_payment.payment_type = Payment.TYPE_FULL
        else:
            open_payment.PaidAmount = paid_amount
            if open_payment.PaidAmount >= open_payment.FullAmount:
                open_payment.PaidAmount = open_payment.FullAmount
                open_payment.payment_type = Payment.TYPE_FULL
            else:
                open_payment.payment_type = Payment.TYPE_INSTALLMENT
        open_payment.recalculate()
        open_payment.save()
        PaymentTransaction.objects.create(
            payment=open_payment,
            amount=open_payment.PaidAmount - old_paid,
            note="دفعة كاملة (إكمال قسط)"
            if open_payment.payment_type == Payment.TYPE_FULL
            else "تحديث دفعة",
        )
        if open_payment.Paymentresult <= 0 and not student.is_payer:
            student.is_payer = True
            student.save(update_fields=["is_payer"])
        return open_payment, PaymentSerializer(open_payment).data

    if full_amount is None:
        # لا يوجد قسط مفتوح: إن كانت كل دفعاته مسدّدة نُعيد الحالة بنجاح
        # بدل خطأ، فالزر يعني «سدّد المتبقي» والمتبقي صفر أصلاً.
        settled = Payment.objects.filter(student=student).order_by("-created_at").first()
        if settled is not None:
            data = PaymentSerializer(settled).data
            data["message"] = "لا يوجد مبلغ مستحق — الحساب مسدّد بالكامل"
            data["detail"] = data["message"]
            data["already_paid"] = True
            return settled, data
        raise ValidationError(
            {
                "FullAmount": "أدخل قيمة القسط الكلي أولاً.",
                "detail": (
                    f"لا توجد دفعات مسجّلة للطالب صاحب الرقم {student.special_number}. "
                    "أرسل FullAmount مع الرقم المميز لإنشاء الدفعة."
                ),
            }
        )

    data = {
        **payload,
        "student": str(student.id),
        "special_number": student.special_number,
        "FullAmount": str(full_amount),
        "PaidAmount": str(paid_amount if paid_amount is not None else full_amount),
        "payment_type": payload.get("payment_type")
        or (
            Payment.TYPE_FULL
            if force_full or paid_amount is None or paid_amount >= full_amount
            else Payment.TYPE_INSTALLMENT
        ),
    }
    serializer = PaymentSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    payment = serializer.save()
    return payment, PaymentSerializer(payment).data


def student_payment_summary(student):
    """ملخّص يملأ شاشة المدفوعات فور إدخال الرقم المميز."""
    payments = list(Payment.objects.filter(student=student).order_by("-created_at"))
    total_full = sum((p.FullAmount for p in payments), Decimal("0"))
    total_paid = sum((p.PaidAmount for p in payments), Decimal("0"))
    remaining = total_full - total_paid
    latest = payments[0] if payments else None
    return {
        "success": True,
        "found": True,
        "student": {
            "id": str(student.id),
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_name": f"{student.first_name} {student.last_name}".strip(),
            "special_number": student.special_number,
            "student_class": student.student_class,
            "parent_number": student.parent_number,
            "student_number": student.student_number,
            "address": student.address,
            "is_payer": student.is_payer,
        },
        # الحقول المسطّحة تسهّل ربط الواجهة مباشرة بحقول النموذج
        "first_name": student.first_name,
        "last_name": student.last_name,
        "student_name": f"{student.first_name} {student.last_name}".strip(),
        "special_number": student.special_number,
        "student_class": student.student_class,
        "parent_number": student.parent_number,
        "student_number": student.student_number,
        "is_payer": student.is_payer,
        "FullAmount": str(latest.FullAmount) if latest else "0.00",
        "PaidAmount": str(latest.PaidAmount) if latest else "0.00",
        "Paymentresult": str(latest.Paymentresult) if latest else "0.00",
        "payment_type": latest.payment_type if latest else "",
        "status": latest.status if latest else "",
        "payment_id": str(latest.id) if latest else None,
        "total_full_amount": str(total_full),
        "total_paid_amount": str(total_paid),
        "total_remaining": str(remaining),
        "payments_count": len(payments),
        "payments": [PaymentSerializer(p).data for p in payments],
    }


@transaction.atomic
def reset_student_payments(student, payments=None):
    """
    تصفير الدفع: إرجاع المدفوع إلى صفر مع بقاء القسط الكلي،
    فيعود الطالب غير مسدّد وتُسجَّل حركة مالية عكسية للتدقيق.
    """
    if payments is None:
        payments = list(Payment.objects.select_for_update().filter(student=student))
    reset_count = 0
    for payment in payments:
        old_paid = payment.PaidAmount
        if old_paid == 0:
            continue
        payment.PaidAmount = Decimal("0")
        payment.payment_type = Payment.TYPE_INSTALLMENT
        payment.recalculate()
        payment.save()
        PaymentTransaction.objects.create(
            payment=payment,
            amount=-old_paid,
            note="تصفير الدفع",
        )
        reset_count += 1

    if student.is_payer:
        student.is_payer = False
        student.save(update_fields=["is_payer"])

    data = student_payment_summary(student)
    data["reset_count"] = reset_count
    data["message"] = "تم تصفير الدفع بنجاح"
    data["detail"] = data["message"]
    return data
