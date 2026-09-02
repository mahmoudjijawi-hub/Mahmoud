"""واجهات التوكن ومديري المعهد المطابقة للـ Collection."""
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import Throttled

from accounts.login_limit import (
    LOCK_MESSAGE,
    clear_failures,
    current_lock,
)
from accounts.models import Manager
from accounts.serializers import CustomTokenObtainPairSerializer, LoginError, ManagerSerializer
from core.permissions import IsManager
from core.throttles import (
    SpecialNumberRateThrottle,
    apply_manager_login_rate_limit_headers,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """POST /api/token/ — مطابق لطلب token، مع قفل بعد 5 محاولات فاشلة لصفحة كلمة المرور."""

    permission_classes = (AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = (SpecialNumberRateThrottle,)

    def post(self, request, *args, **kwargs):
        # قبل أي محاولة دخول: ضمان أن حساب المدير وكلمة مروره جاهزان من الإعدادات
        try:
            from accounts.bootstrap import ensure_admin_credentials

            ensure_admin_credentials()
        except Exception:
            pass
        from core.throttles import _is_special_number_attempt

        password_page = not _is_special_number_attempt(request)
        if password_page:
            blocked, wait, info = current_lock()
            request._manager_login_rate_limit = info
            if blocked:
                raise LoginError(
                    LOCK_MESSAGE,
                    "too_many_requests",
                    wait=max(int(wait or 120), 1),
                    locked=True,
                )

        response = super().post(request, *args, **kwargs)
        if password_page and _login_issued_token(response):
            _blocked, _wait, info = clear_failures()
            request._manager_login_rate_limit = info
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        return apply_manager_login_rate_limit_headers(request, response)

    def throttled(self, request, wait):
        seconds = int(wait) if wait else 120
        raise Throttled(
            wait=seconds,
            detail=LOCK_MESSAGE,
        )


def _login_issued_token(response):
    if getattr(response, "status_code", None) != 200:
        return False
    data = getattr(response, "data", None) or {}
    if not hasattr(data, "get"):
        return False
    return bool(data.get("access") or data.get("token") or data.get("accessToken"))


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
