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
        جسم مثال:
        {"student": "<uuid>", "FullAmount": "1000"}
        أو {"special_number": "22", "FullAmount": "1000"}
        """
        payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        payload["payment_type"] = Payment.TYPE_FULL
        # إن وُجد القسط الكلي ولم يُرسل المدفوع نعبّئه تلقائياً في الـ Serializer
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(self.get_serializer(payment).data, status=status.HTTP_201_CREATED)

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
