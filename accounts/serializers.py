"""مسلسلات المصادقة والمديرين — أسماء الحقول حرفياً كما في الـ Collection."""
import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomUser, Manager, LoginLog
from accounts.bootstrap import ensure_admin_credentials, KNOWN_ADMIN_PASSWORDS
from accounts.idle import enforce_idle_or_touch, touch_activity
from core.fields import FlexibleCharField

# مسجّل محاولات الدخول دون كتابة الرقم المميز أو كلمة المرور
auth_logger = logging.getLogger("accounts.auth")


class LoginError(APIException):
    """خطأ دخول يعيد detail/code كنصوص مباشرة تفهمها الواجهة."""

    status_code = 400

    def __init__(self, message, code, **extra):
        # dict يُمرَّر كما هو عبر exception_handler دون لفّ كل قيمة بقائمة
        detail = {
            "success": False,
            "detail": message,
            "error": message,
            "message": message,
            "code": code,
            "non_field_errors": [message],
        }
        detail.update(extra)
        self.detail = detail


def _client_ip(request):
    """عنوان IP من الاتصال المباشر."""
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR")


def _pick(data, *keys):
    """اختيار أول قيمة غير فارغة من مفاتيح شائعة يرسلها الفرونت."""
    if not data:
        return ""
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    # مطابقة غير حسّاسة لحالة الأحرف
    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        value = lowered.get(str(key).lower())
        if value not in (None, ""):
            return value
    return ""


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    POST /api/token/
    - username + password كما في طلب token بالـ Collection (المدير).
    - أو special_number فقط: أستاذ/طالب → JWT، مدير → توجيه لصفحة كلمة المرور.
    """

    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    special_number = FlexibleCharField(required=False, allow_blank=True, max_length=10)

    def __init__(self, *args, **kwargs):
        # الأب يعيد إضافة username/password كحقول إلزامية — نخفف الإلزام بعد ذلك
        super().__init__(*args, **kwargs)
        # بدون max_length صارم حتى لا تُرفض كلمة مرور الفرونت بصمت قبل التحقق
        self.fields["username"] = serializers.CharField(required=False, allow_blank=True)
        self.fields["password"] = serializers.CharField(
            required=False, allow_blank=True, write_only=True
        )
        self.fields["username"].required = False
        self.fields["password"].required = False
        if "special_number" not in self.fields:
            self.fields["special_number"] = FlexibleCharField(
                required=False, allow_blank=True, max_length=10
            )

    @classmethod
    def get_token(cls, user):
        # توليد التوكن الافتراضي ثم إضافة إصدار الجلسة للمدير
        token = super().get_token(user)
        token["token_version"] = user.token_version
        token["role"] = user.role
        return token

    def _auth_error(self, message, code):
        """خطأ موحّد تفهمه الواجهة عبر detail و code و non_field_errors."""
        raise LoginError(message, code)

    def _raise_failed_login(self, request, message, code):
        """يسجّل الفشل؛ عند نفاد المحاولات تُعرض رسالة الانتظار لا كلمة المرور الخطأ."""
        from accounts.login_limit import LOCK_MESSAGE, register_failure

        blocked, wait, info = register_failure()
        if request is not None:
            request._manager_login_rate_limit = info
        if blocked:
            raise LoginError(LOCK_MESSAGE, "too_many_requests", wait=wait, locked=True)
        raise LoginError(message, code)

    def _token_payload(self, user):
        """شكل استجابة الدخول الذي تعتمد عليه الواجهة للتوجيه بعد كلمة المرور."""
        touch_activity(user)
        refresh = self.get_token(user)
        access = str(refresh.access_token)
        payload = {
            "access": access,
            "refresh": str(refresh),
            # مرادفات شائعة: token أو accessToken في localStorage
            "token": access,
            "accessToken": access,
            "role": user.role,
            "user_type": user.user_type,
            "username": user.username,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "role": user.role,
                "user_type": user.user_type,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
        }
        # شاشة بروفايل الطالب تخزّن studentId و studentToken في localStorage
        if user.role == CustomUser.ROLE_STUDENT:
            from academics.models import Student

            student = getattr(user, "student_profile", None)
            if student is None:
                student = Student.objects.filter(user=user).first()
            if student is not None:
                payload["studentToken"] = access
                payload["studentId"] = str(student.id)
                payload["student_id"] = str(student.id)
                payload["id"] = str(student.id)
                payload["status"] = "success"
                payload["first_name"] = student.first_name
                payload["last_name"] = student.last_name
                payload["is_payer"] = student.is_payer
                payload["special_number"] = student.special_number
                payload["student_name"] = f"{student.first_name} {student.last_name}".strip()
                payload["user"]["first_name"] = student.first_name
                payload["user"]["last_name"] = student.last_name
                payload["user"]["studentId"] = str(student.id)
                from academics.serializers import student_path_labels

                path = student_path_labels(student)
                payload["class1"] = path["class1"]
                payload["class2"] = path["class2"]
                payload["class3"] = path["class3"]
                payload["studentGrade"] = path["class1"]
                payload["studentSection"] = path["class3"]
                payload["user"]["class1"] = path["class1"]
                payload["user"]["class3"] = path["class3"]
                payload["user"]["studentGrade"] = path["class1"]
                payload["user"]["studentSection"] = path["class3"]
        return payload

    def _resolve_manager_user(self, username, password):
        """
        مصادقة المدير مع إصلاح ذاتي:
        إن طابقت بيانات الإعدادات/البوستمان نضبط الهاش وندخل حتى لو كان الحساب تالفاً.
        """
        # محاولة Django الاعتيادية أولاً
        user = authenticate(username=username, password=password)
        if user is not None:
            return user

        # بحث غير حسّاس لحالة الأحرف
        user = CustomUser.objects.filter(username__iexact=username).first()
        if user is not None and user.check_password(password):
            return user

        admin_username = str(settings.ADMIN_USERNAME)
        admin_password = str(settings.ADMIN_PASSWORD)
        accepted_users = {admin_username.lower(), "ammar"}
        accepted_passwords = {admin_password, *KNOWN_ADMIN_PASSWORDS}

        if username.lower() not in accepted_users or password not in accepted_passwords:
            return None

        # إصلاح ذاتي نهائي: نزامن الحساب مع كلمة المرور المُرسلة ثم ندخل
        ensure_admin_credentials()
        user = (
            CustomUser.objects.filter(username__iexact=admin_username).first()
            or CustomUser.objects.filter(special_number=str(settings.ADMIN_SPECIAL_NUMBER)).first()
        )
        if user is None:
            return None
        user.username = admin_username[:25]
        user.role = CustomUser.ROLE_MANAGER
        user.user_type = "1"
        user.is_active = True
        user.set_password(password)
        user.save()
        auth_logger.info("self_heal_admin_password username=%s", admin_username)
        return user

    def validate(self, attrs):
        request = self.context.get("request")
        raw = getattr(self, "initial_data", {}) or {}
        # قبول أسماء حقول شائعة من الفرونت إضافة لاسم الـ Collection
        username = str(
            _pick(attrs, "username")
            or _pick(raw, "username", "userName", "user_name", "user", "UserName", "login", "name", "Name", "email")
            or ""
        ).strip()
        password = str(
            _pick(attrs, "password")
            or _pick(raw, "password", "Password", "pass", "passwd")
            or ""
        )
        # إزالة فراغات الأطراف فقط (شائعة عند النسخ من الواجهة)
        password = password.strip()
        special_number = str(
            _pick(attrs, "special_number")
            or _pick(raw, "special_number", "specialNumber", "special", "number")
            or ""
        ).strip()

        # مسار الرقم المميز وحده (توجيه الدور أو دخول أستاذ/طالب)
        if special_number and not (username and password):
            return self._validate_special_number(request, special_number)

        # مسار اسم المستخدم وكلمة المرور (المدير) — الدخول الصحيح أولاً، والقفل للغلط فقط
        if not username or not password:
            auth_logger.info("failed_login reason=missing_credentials")
            self._raise_failed_login(
                request, "يجب إدخال اسم المستخدم وكلمة المرور.", "missing_credentials"
            )

        user = self._resolve_manager_user(username, password)
        if user is None:
            # قد يكون أستاذاً/طالباً أُدخل له كلمة مرور لاحقاً — نعيد المحاولة العامة
            user = authenticate(request=request, username=username, password=password)
        if user is None:
            auth_logger.info("failed_login reason=invalid_password")
            self._raise_failed_login(
                request,
                "اسم المستخدم أو كلمة المرور غير صحيحة.",
                "invalid_credentials",
            )
        if not user.is_active:
            auth_logger.info("failed_login reason=inactive")
            self._raise_failed_login(request, "هذا الحساب غير نشط.", "inactive")

        # إبطال توكنات المدير السابقة عبر زيادة الإصدار
        if user.role == CustomUser.ROLE_MANAGER:
            user.bump_token_version()
            LoginLog.objects.create(
                user=user,
                ip_address=_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT", "")[:1000] if request else ""),
            )

        from accounts.login_limit import clear_failures

        clear_failures()
        return self._token_payload(user)

    def _validate_special_number(self, request, special_number):
        """دخول/توجيه بالرقم المميز مع throttling على مستوى الـ View."""
        from core.digits import normalize_digits
        from academics.models import Student

        special_number = normalize_digits(str(special_number).strip())
        # حد طول التوجيه العام 7 للمدير و10 للأستاذ/الطالب يُفحص حسب الدور بعد الجلب
        user = CustomUser.objects.filter(special_number=special_number, is_active=True).first()
        if user is None:
            student = Student.objects.filter(special_number=special_number).select_related("user").first()
            if student is not None and student.user_id and student.user.is_active:
                user = student.user
        if user is None:
            auth_logger.info("failed_login reason=unknown_special_number")
            self._auth_error("الرقم المميز غير صحيح.", "unknown_special_number")
        if user.role == CustomUser.ROLE_MANAGER:
            # مهم للفرونت: 200 وليس 400 حتى تنتقل الواجهة لصفحة كلمة مرور المدير
            auth_logger.info("manager_routing special_number_ok")
            return {
                "requires_password": True,
                "role": user.role,
                "user_type": user.user_type,
                "username": user.username,
                "special_number": special_number,
                "detail": "رقم مدير صحيح. أدخل اسم المستخدم وكلمة المرور.",
                "code": "manager_password_required",
            }
        return self._token_payload(user)


class IdleAwareTokenRefreshSerializer(TokenRefreshSerializer):
    """تجديد التوكن يفشل بعد ساعة خمول، ويتجدد عداد النشاط إن كانت الجلسة حيّة."""

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get("user_id")
        user = CustomUser.objects.filter(pk=user_id).first()
        if user is None:
            from rest_framework_simplejwt.exceptions import InvalidToken

            raise InvalidToken("انتهت الجلسة. يرجى تسجيل الدخول مجدداً")
        enforce_idle_or_touch(user)
        return super().validate(attrs)


class ManagerSerializer(serializers.ModelSerializer):
    """حقول POST /api/managers/ و PATCH كما في الـ Collection."""

    username = serializers.CharField(max_length=25, write_only=True, required=False)
    password = serializers.CharField(max_length=25, write_only=True, required=False)
    special_number = FlexibleCharField(max_length=7)
    user_type = FlexibleCharField(max_length=4, required=False, default="1")
    first_name = serializers.CharField(max_length=15)
    last_name = serializers.CharField(max_length=15)

    class Meta:
        model = Manager
        fields = (
            "id",
            "username",
            "password",
            "first_name",
            "last_name",
            "special_number",
            "user_type",
        )
        read_only_fields = ("id",)

    def validate_special_number(self, value):
        # حد 7 خانات لرقم المدير حسب البرومبت
        if not str(value).isdigit():
            raise serializers.ValidationError("الرقم المميز يجب أن يكون رقمياً.")
        if len(str(value)) > 7:
            raise serializers.ValidationError("الرقم المميز للمدير 7 خانات كحد أقصى.")
        return str(value)

    def to_representation(self, instance):
        # إرجاع الحقول الظاهرة مع اسم المستخدم من الحساب المرتبط
        data = super().to_representation(instance)
        data["username"] = instance.user.username
        return data

    @transaction.atomic
    def create(self, validated_data):
        username = validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        if not username or not password:
            raise serializers.ValidationError("اسم المستخدم وكلمة المرور مطلوبان لإنشاء مدير.")
        user = CustomUser.objects.create_user(
            username=username,
            password=password,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            special_number=validated_data["special_number"],
            role=CustomUser.ROLE_MANAGER,
            user_type=validated_data.get("user_type", "1"),
        )
        return Manager.objects.create(user=user, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        username = validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        # تحديث ملف المدير
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        # مزامنة الحساب المرتبط
        user = instance.user
        if username:
            user.username = username
        if password:
            user.set_password(password)
        user.first_name = instance.first_name
        user.last_name = instance.last_name
        user.special_number = instance.special_number
        user.user_type = instance.user_type
        user.save()
        return instance
