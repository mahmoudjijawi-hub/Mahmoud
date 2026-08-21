"""واجهة /api/payments/ مع حد معدل خاص ودعم زر الدفعة الكاملة."""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsManagerOrReadOnlyAuthenticated
from core.throttles import PaymentRateThrottle
from payments.models import Payment
from payments.serializers import PaymentSerializer


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    throttle_classes = (PaymentRateThrottle,)
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

    @action(detail=False, methods=["post"], url_path="full")
    def full_payment(self, request):
        """
        زر دفعة كاملة:
        POST /api/payments/full/
        """
        payload = dict(request.data.items()) if hasattr(request.data, "items") else dict(request.data)
        payload["payment_type"] = Payment.TYPE_FULL
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)

    def create(self, request, *args, **kwargs):
        """إنشاء دفعة مع رسالة خطأ أوضح عند فشل زر الدفعة الكاملة."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        headers = self.get_success_headers(serializer.data)
        return Response(
            self.get_serializer(payment).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @action(detail=True, methods=["post"], url_path="pay-full")
    def pay_remaining_full(self, request, pk=None):
        """
        إكمال دفعة موجودة بالكامل:
        POST /api/payments/{id}/pay-full/
        يضبط PaidAmount = FullAmount والمتبقي = 0.
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
