"""واجهات التوكن ومديري المعهد المطابقة للـ Collection."""
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import Throttled

from accounts.models import Manager
from accounts.serializers import CustomTokenObtainPairSerializer, ManagerSerializer
from core.permissions import IsManager
from core.throttles import (
    SpecialNumberRateThrottle,
    ManagerPasswordLoginThrottle,
    apply_manager_login_rate_limit_headers,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """POST /api/token/ — مطابق لطلب token، مع حد 5 محاولات/دقيقة لصفحة كلمة مرور المدير."""

    permission_classes = (AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = (ManagerPasswordLoginThrottle, SpecialNumberRateThrottle)

    def post(self, request, *args, **kwargs):
        # قبل أي محاولة دخول: ضمان أن حساب المدير وكلمة مروره جاهزان من الإعدادات
        try:
            from accounts.bootstrap import ensure_admin_credentials

            ensure_admin_credentials()
        except Exception:
            pass
        return super().post(request, *args, **kwargs)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        return apply_manager_login_rate_limit_headers(request, response)

    def throttled(self, request, wait):
        seconds = int(wait) if wait else 120
        raise Throttled(
            wait=seconds,
            detail="لقد قمت بعدة محاولات كثيرة، يرجى المحاولة مرة أخرى بعد دقيقتين.",
        )


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
