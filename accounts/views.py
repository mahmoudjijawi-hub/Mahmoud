"""واجهات التوكن ومديري المعهد المطابقة للـ Collection."""
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.models import Manager
from accounts.serializers import CustomTokenObtainPairSerializer, ManagerSerializer
from core.permissions import IsManager
from core.throttles import LoginRateThrottle, SpecialNumberRateThrottle


class CustomTokenObtainPairView(TokenObtainPairView):
    """POST /api/token/ — مطابق لطلب token، مع حد معدل مزدوج."""

    permission_classes = (AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = (LoginRateThrottle, SpecialNumberRateThrottle)
    throttle_scope = "login"


class ManagerViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/managers/
    PATCH/DELETE /api/managers/{uuid}/
    """

    serializer_class = ManagerSerializer
    permission_classes = (IsManager,)
    queryset = Manager.objects.select_related("user").all()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        # حذف فعلي كما في طلب delete user بالـ Collection
        instance = self.get_object()
        user = instance.user
        self.perform_destroy(instance)
        # حذف الحساب المرتبط بعد الملف
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
