"""واجهة /api/payments/ مع حد معدل خاص."""
from rest_framework import viewsets

from core.permissions import IsManagerOrReadOnlyAuthenticated
from core.throttles import PaymentRateThrottle
from payments.models import Payment
from payments.serializers import PaymentSerializer


class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    throttle_classes = (PaymentRateThrottle,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = Payment.objects.select_related("student").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user)
        special = self.request.query_params.get("special_number")
        if special:
            qs = qs.filter(student__special_number=str(special))
        return qs
