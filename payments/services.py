"""خدمة دفع موحّدة لزر الدفع — إنشاء أو إكمال دفعة كاملة."""
import json

from django.db import transaction
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


@transaction.atomic
def execute_payment(payload, force_full=False):
    """
    تنفيذ دفع مرن يُرجع (payment, response_dict).
    - يكمل قسطاً مفتوحاً إن وُجد
    - ينشئ دفعة كاملة عند توفر المبلغ
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
        raise ValidationError(
            {
                "FullAmount": "القسط الكلي مطلوب لإتمام الدفع.",
                "detail": "أرسل FullAmount أو PaidAmount مع رقم/معرف الطالب.",
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
