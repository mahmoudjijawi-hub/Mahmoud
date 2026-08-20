"""مسلسلات المصادقة والمديرين — أسماء الحقول حرفياً كما في الـ Collection."""
import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomUser, Manager, LoginLog
from core.fields import FlexibleCharField

# مسجّل محاولات الدخول دون كتابة الرقم المميز أو كلمة المرور
auth_logger = logging.getLogger("accounts.auth")


def _client_ip(request):
    """عنوان IP من الاتصال المباشر."""
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR")


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    POST /api/token/
    - username + password كما في طلب token بالـ Collection (المدير).
    - أو special_number فقط للأستاذ/الطالب (ميزة البرومبت دون كسر جسم الـ Collection).
    """

    username = serializers.CharField(required=False, allow_blank=True, max_length=25)
    password = serializers.CharField(required=False, allow_blank=True, max_length=25, write_only=True)
    special_number = FlexibleCharField(required=False, allow_blank=True, max_length=10)

    def __init__(self, *args, **kwargs):
        # الأب يعيد إضافة username/password كحقول إلزامية — نخفف الإلزام بعد ذلك
        super().__init__(*args, **kwargs)
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

    def validate(self, attrs):
        request = self.context.get("request")
        username = (attrs.get("username") or "").strip()
        password = attrs.get("password") or ""
        special_number = (attrs.get("special_number") or "").strip()

        # مسار الرقم المميز وحده (طالب/أستاذ)
        if special_number and not (username and password):
            return self._validate_special_number(request, special_number)

        # مسار اسم المستخدم وكلمة المرور (المدير) — مطابق للـ Collection
        if not username or not password:
            auth_logger.info("failed_login reason=missing_credentials")
            raise serializers.ValidationError("يجب إدخال اسم المستخدم وكلمة المرور.")

        user = authenticate(request=request, username=username, password=password)
        if user is None:
            auth_logger.info("failed_login reason=invalid_password")
            raise serializers.ValidationError("اسم المستخدم أو كلمة المرور غير صحيحة.")
        if not user.is_active:
            auth_logger.info("failed_login reason=inactive")
            raise serializers.ValidationError("هذا الحساب غير نشط.")

        # إبطال توكنات المدير السابقة عبر زيادة الإصدار
        if user.role == CustomUser.ROLE_MANAGER:
            user.bump_token_version()
            LoginLog.objects.create(
                user=user,
                ip_address=_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT", "")[:1000] if request else ""),
            )

        refresh = self.get_token(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    def _validate_special_number(self, request, special_number):
        """دخول بالرقم المميز مع throttling على مستوى الـ View."""
        # حد طول التوجيه العام 7 للمدير و10 للأستاذ/الطالب يُفحص حسب الدور بعد الجلب
        user = CustomUser.objects.filter(special_number=special_number, is_active=True).first()
        if user is None:
            auth_logger.info("failed_login reason=unknown_special_number")
            raise serializers.ValidationError("الرقم المميز غير صحيح.")
        if user.role == CustomUser.ROLE_MANAGER:
            # المرحلة الأولى فقط: لا نُصدر JWT قبل اسم المستخدم وكلمة المرور
            raise serializers.ValidationError(
                "هذا رقم مدير. الرجاء تسجيل الدخول باسم المستخدم وكلمة المرور."
            )
        refresh = self.get_token(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


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
