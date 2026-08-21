"""واجهة /api/payments/ مع حد معدل خاص ودعم زر الدفعة الكاملة."""
import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from core.permissions import IsManagerOrReadOnlyAuthenticated
from core.throttles import PaymentRateThrottle
from payments.models import Payment
from payments.serializers import PaymentSerializer

logger = logging.getLogger("payments")


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    throttle_classes = (PaymentRateThrottle,)
    parser_classes = (JSONParser, FormParser, MultiPartParser)
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

    def create(self, request, *args, **kwargs):
        """إنشاء دفعة — يسجّل جسم الطلب عند الفشل لتسهيل التشخيص."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("payment_create_failed data=%s errors=%s", dict(request.data), serializer.errors)
            return Response(
                {
                    "success": False,
                    "detail": "تعذر إتمام الدفع. تحقق من بيانات الطالب والمبلغ.",
                    "errors": serializer.errors,
                    **serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment = serializer.save()
        out = self.get_serializer(payment).data
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post", "put"], url_path="full")
    def full_payment(self, request):
        """
        زر دفعة كاملة:
        POST /api/payments/full/
        """
        payload = {k: v for k, v in request.data.items()} if hasattr(request.data, "items") else dict(request.data)
        payload["payment_type"] = Payment.TYPE_FULL
        serializer = self.get_serializer(data=payload)
        if not serializer.is_valid():
            logger.warning("payment_full_failed data=%s errors=%s", payload, serializer.errors)
            return Response(
                {
                    "success": False,
                    "detail": "تعذر إتمام الدفعة الكاملة.",
                    "errors": serializer.errors,
                    **serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment = serializer.save()
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post", "put"], url_path="full-payment")
    def full_payment_alias(self, request):
        """مرادف إضافي: POST /api/payments/full-payment/"""
        return self.full_payment(request)

    @action(detail=True, methods=["post", "put", "patch"], url_path="pay-full")
    def pay_remaining_full(self, request, pk=None):
        """
        إكمال دفعة موجودة بالكامل:
        POST /api/payments/{id}/pay-full/
        """
        payment = self.get_object()
        serializer = self.get_serializer(
            payment,
            data={
                "FullAmount": payment.FullAmount,
                "PaidAmount": payment.FullAmount,
                "payment_type": Payment.TYPE_FULL,
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
