"""واجهة /api/payments/ مع حد معدل خاص ودعم زر الدفعة الكاملة."""
import logging
import uuid

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.permissions import IsManagerOrReadOnlyAuthenticated
from core.throttles import PaymentRateThrottle
from payments.models import Payment
from payments.parsers import PAYMENT_PARSERS
from payments.serializers import PaymentSerializer, _resolve_student, _pick
from payments.services import (
    execute_payment,
    extract_raw_payload,
    reset_student_payments,
    student_payment_summary,
)

logger = logging.getLogger("payments")


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    throttle_classes = (PaymentRateThrottle,)
    throttle_scope = "payments"
    parser_classes = PAYMENT_PARSERS
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def get_queryset(self):
        qs = Payment.objects.select_related("student").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user)
        params = self.request.query_params
        special = (
            params.get("special_number")
            or params.get("specialNumber")
            or params.get("number")
        )
        if special:
            qs = qs.filter(student__special_number=str(special).strip())
        return qs

    def get_object(self):
        """يقبل معرّف الدفعة (UUID) أو الرقم المميز للطالب مباشرة."""
        lookup = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        if lookup and not _is_uuid(lookup):
            queryset = self.filter_queryset(self.get_queryset())
            payment = (
                queryset.filter(student__special_number=str(lookup).strip())
                .order_by("-created_at")
                .first()
            )
            if payment is None:
                raise Http404("لا توجد دفعة لهذا الرقم المميز.")
            self.check_object_permissions(self.request, payment)
            return payment
        return super().get_object()

    def _student_from_request(self, request, pk=None):
        """استخراج الطالب من الجسم أو الاستعلام أو المسار."""
        payload = extract_raw_payload(request)
        student = _resolve_student(
            _pick(payload, "student", "student_id", "studentId")
            or _pick(payload, "special_number", "specialNumber", "number")
        )
        if student is None and pk:
            student = _resolve_student(pk)
            if student is None:
                payment = Payment.objects.filter(pk=pk).first() if _is_uuid(pk) else None
                student = payment.student if payment else None
        return student, payload

    @action(detail=False, methods=["get", "post"], url_path="lookup")
    def lookup(self, request):
        """
        بيانات الطالب ومدفوعاته من الرقم المميز:
        GET /api/payments/lookup/?special_number=333
        تُستخدم لملء بقية الحقول فور إدخال الرقم.
        """
        student, _ = self._student_from_request(request)
        if student is None:
            return Response(
                {
                    "success": False,
                    "found": False,
                    "detail": "لا يوجد طالب بهذا الرقم المميز.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(student_payment_summary(student), status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="summary")
    def student_summary(self, request, pk=None):
        """GET /api/payments/{رقم مميز}/summary/"""
        student, _ = self._student_from_request(request, pk=pk)
        if student is None:
            return Response(
                {"success": False, "found": False, "detail": "لا يوجد طالب بهذا الرقم المميز."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(student_payment_summary(student), status=status.HTTP_200_OK)

    def _reset_response(self, request, pk=None):
        student, payload = self._student_from_request(request, pk=pk)
        if student is None:
            logger.warning("payment_reset_failed data=%s", payload)
            return Response(
                {
                    "success": False,
                    "detail": "حدد الطالب بالرقم المميز أو معرّفه لتصفير الدفع.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(reset_student_payments(student), status=status.HTTP_200_OK)

    @action(detail=False, methods=["post", "put", "patch"], url_path="reset")
    def reset(self, request):
        """زر تصفير الدفع: POST /api/payments/reset/ مع special_number"""
        return self._reset_response(request)

    @action(detail=True, methods=["post", "put", "patch"], url_path="reset")
    def reset_detail(self, request, pk=None):
        """POST /api/payments/{رقم مميز أو معرّف}/reset/"""
        return self._reset_response(request, pk=pk)

    @action(detail=False, methods=["post", "put", "patch"], url_path="zero")
    def zero(self, request):
        """مرادف: POST /api/payments/zero/"""
        return self._reset_response(request)

    def _pay_response(self, request, force_full=False):
        payload = extract_raw_payload(request)
        try:
            payment, data = execute_payment(payload, force_full=force_full)
        except ValidationError as exc:
            detail = getattr(exc, "detail", str(exc))
            logger.warning("payment_failed data=%s errors=%s", payload, detail)
            body = {
                "success": False,
                "detail": "تعذر إتمام الدفع. تحقق من بيانات الطالب والمبلغ.",
                "errors": detail,
            }
            if isinstance(detail, dict):
                body.update(detail)
            return Response(body, status=status.HTTP_400_BAD_REQUEST)
        # 200 وليس 201 فقط — كثير من واجهات الفرونت تفحص status === 200
        return Response(data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        """إنشاء/إكمال دفعة من زر الدفع."""
        return self._pay_response(request, force_full=False)

    def update(self, request, *args, **kwargs):
        """PUT كامل — إن وُجد pk نحدّث، وإلا نعاملها كإنشاء دفع."""
        if kwargs.get("pk"):
            return super().update(request, *args, **kwargs)
        return self._pay_response(request, force_full=True)

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        if isinstance(response.data, dict):
            response.data.setdefault("success", True)
        return response

    @action(detail=False, methods=["post", "put", "patch"], url_path="full")
    def full_payment(self, request):
        """POST /api/payments/full/"""
        return self._pay_response(request, force_full=True)

    @action(detail=False, methods=["post", "put", "patch"], url_path="full-payment")
    def full_payment_alias(self, request):
        """POST /api/payments/full-payment/"""
        return self.full_payment(request)

    @action(detail=False, methods=["post", "put", "patch"], url_path="pay")
    def pay_alias(self, request):
        """POST /api/payments/pay/"""
        return self._pay_response(request, force_full=True)

    @action(detail=True, methods=["post", "put", "patch"], url_path="pay-full")
    def pay_remaining_full(self, request, pk=None):
        """POST /api/payments/{id}/pay-full/"""
        payment = self.get_object()
        payload = extract_raw_payload(request)
        payload["student"] = str(payment.student_id)
        payload["FullAmount"] = payload.get("FullAmount") or str(payment.FullAmount)
        payload["PaidAmount"] = str(payment.FullAmount)
        payload["payment_type"] = Payment.TYPE_FULL
        try:
            payment, data = execute_payment(payload, force_full=True)
        except ValidationError as exc:
            return Response(
                {"success": False, "detail": "تعذر إكمال الدفعة.", "errors": exc.detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data, status=status.HTTP_200_OK)
