"""مسلسلات الأستاذ والطالب بأسماء حقول الـ Collection حرفياً."""
from django.db import transaction
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination

from accounts.models import CustomUser
from academics.files import validate_cv_file
from academics.models import Teacher, Student
from core.fields import FlexibleBooleanField, FlexibleCharField, GenderField


class StudentPagination(PageNumberPagination):
    """ترقيم إجباري لقائمة الطلاب حتى لا تُرجع آلاف السجلات."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TeacherSerializer(serializers.ModelSerializer):
    """POST /api/teachers/ و PATCH /api/teachers/{uuid}/"""

    user = serializers.UUIDField(required=False, allow_null=True)
    first_name = serializers.CharField(max_length=15)
    last_name = serializers.CharField(max_length=15)
    special_number = FlexibleCharField(max_length=10)
    gender = GenderField(required=False)
    teacher_number = FlexibleCharField(max_length=10)
    expertise = serializers.CharField(max_length=30)
    cv = serializers.CharField(max_length=175, required=False, allow_blank=True)
    confirm_special_number = FlexibleCharField(max_length=10, required=False, write_only=True)

    class Meta:
        model = Teacher
        fields = (
            "id",
            "user",
            "first_name",
            "last_name",
            "special_number",
            "gender",
            "teacher_number",
            "expertise",
            "cv",
            "confirm_special_number",
        )
        read_only_fields = ("id",)

    def validate_special_number(self, value):
        if not str(value).isdigit():
            raise serializers.ValidationError("الرقم المميز يجب أن يكون رقمياً.")
        if len(str(value)) > 10:
            raise serializers.ValidationError("الرقم المميز 10 خانات كحد أقصى.")
        return str(value)

    def validate_teacher_number(self, value):
        if not str(value).isdigit():
            raise serializers.ValidationError("رقم هاتف الأستاذ يجب أن يكون رقمياً وبحد أقصى 10 خانات.")
        return str(value)

    def validate(self, attrs):
        confirm = attrs.pop("confirm_special_number", None)
        special = attrs.get("special_number")
        if confirm is not None and special is not None and str(confirm) != str(special):
            raise serializers.ValidationError({"special_number": "تأكيد الرقم المميز غير مطابق."})
        # إن رُفع ملف ضمن الطلب متعدد الأجزاء نتحقق منه
        request = self.context.get("request")
        if request is not None and request.FILES.get("cv"):
            validate_cv_file(request.FILES["cv"])
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["user"] = str(instance.user_id)
        return data

    def _gender_value(self, value):
        # حفظ المدخل كنص ليقبل true و Yes
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value) if value is not None else ""

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("user", None)
        special = validated_data["special_number"]
        gender = self._gender_value(validated_data.get("gender", ""))
        request = self.context.get("request")
        cv_file = request.FILES.get("cv") if request is not None else None
        cv_text = validated_data.get("cv", "")
        if cv_file and not cv_text:
            cv_text = cv_file.name[:175]
        user = CustomUser.objects.create_user(
            username=f"t{special}"[:25],
            password=None,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            special_number=special,
            role=CustomUser.ROLE_TEACHER,
            user_type="2",
        )
        teacher = Teacher.objects.create(
            user=user,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            special_number=special,
            gender=gender,
            teacher_number=validated_data["teacher_number"],
            expertise=validated_data["expertise"],
            cv=cv_text or "",
            cv_file=cv_file,
        )
        return teacher

    @transaction.atomic
    def update(self, instance, validated_data):
        user_id = validated_data.pop("user", None)
        if user_id:
            instance.user_id = user_id
        if "gender" in validated_data:
            validated_data["gender"] = self._gender_value(validated_data["gender"])
        request = self.context.get("request")
        if request is not None and request.FILES.get("cv"):
            instance.cv_file = request.FILES["cv"]
            if not validated_data.get("cv"):
                validated_data["cv"] = request.FILES["cv"].name[:175]
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        user = instance.user
        user.first_name = instance.first_name
        user.last_name = instance.last_name
        user.special_number = instance.special_number
        user.save(update_fields=["first_name", "last_name", "special_number"])
        return instance


class StudentSerializer(serializers.ModelSerializer):
    """POST /api/students/ و PATCH /api/students/{uuid}/"""

    first_name = serializers.CharField(max_length=15)
    last_name = serializers.CharField(max_length=15)
    special_number = FlexibleCharField(max_length=10)
    student_class = FlexibleCharField(max_length=20)
    parent_number = FlexibleCharField(max_length=10)
    student_number = FlexibleCharField(max_length=10)
    address = serializers.CharField(max_length=30)
    personal_notes = serializers.CharField(max_length=25, required=False, allow_blank=True)
    is_payer = FlexibleBooleanField(required=False)
    class1 = serializers.CharField(max_length=30, required=False, allow_blank=True)
    class2 = serializers.CharField(max_length=30, required=False, allow_blank=True)
    class3 = serializers.CharField(max_length=30, required=False, allow_blank=True)
    confirm_special_number = FlexibleCharField(max_length=10, required=False, write_only=True)

    class Meta:
        model = Student
        fields = (
            "id",
            "first_name",
            "last_name",
            "special_number",
            "student_class",
            "parent_number",
            "student_number",
            "address",
            "personal_notes",
            "is_payer",
            "class1",
            "class2",
            "class3",
            "confirm_special_number",
        )
        read_only_fields = ("id",)

    def validate_special_number(self, value):
        if not str(value).isdigit():
            raise serializers.ValidationError("الرقم المميز يجب أن يكون رقمياً.")
        if len(str(value)) > 10:
            raise serializers.ValidationError("الرقم المميز 10 خانات كحد أقصى.")
        return str(value)

    def _phone(self, value, field_ar):
        if not str(value).isdigit():
            raise serializers.ValidationError(f"{field_ar} يجب أن يكون رقمياً وبحد أقصى 10 خانات.")
        return str(value)

    def validate_parent_number(self, value):
        return self._phone(value, "رقم هاتف الأهل")

    def validate_student_number(self, value):
        return self._phone(value, "رقم هاتف الطالب")

    def validate(self, attrs):
        confirm = attrs.pop("confirm_special_number", None)
        special = attrs.get("special_number")
        if confirm is not None and special is not None and str(confirm) != str(special):
            raise serializers.ValidationError({"special_number": "تأكيد الرقم المميز غير مطابق."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        special = validated_data["special_number"]
        user = CustomUser.objects.create_user(
            username=f"s{special}"[:25],
            password=None,
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            special_number=special,
            role=CustomUser.ROLE_STUDENT,
            user_type="3",
        )
        return Student.objects.create(user=user, **validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        raw = getattr(self, "initial_data", {}) or {}
        became_payer = (
            "is_payer" in validated_data
            and validated_data.get("is_payer") is True
            and not instance.is_payer
        )
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        user = instance.user
        user.first_name = instance.first_name
        user.last_name = instance.last_name
        user.special_number = instance.special_number
        user.save(update_fields=["first_name", "last_name", "special_number"])

        # إن ضغط زر الدفع من شاشة الطالب (is_payer=true + مبلغ) نُنشئ دفعة كاملة تلقائياً
        if became_payer:
            from decimal import Decimal, InvalidOperation
            from payments.models import Payment, PaymentTransaction

            amount_raw = (
                raw.get("FullAmount")
                or raw.get("full_amount")
                or raw.get("fullAmount")
                or raw.get("amount")
                or raw.get("PaidAmount")
                or raw.get("paid_amount")
            )
            if amount_raw not in (None, ""):
                try:
                    amount = Decimal(str(amount_raw))
                except (InvalidOperation, TypeError, ValueError):
                    amount = None
                if amount is not None and amount > 0:
                    payment = Payment(
                        student=instance,
                        FullAmount=amount,
                        PaidAmount=amount,
                        Paymentresult=Decimal("0"),
                        payment_type=Payment.TYPE_FULL,
                    )
                    payment.recalculate()
                    payment.save()
                    PaymentTransaction.objects.create(
                        payment=payment,
                        amount=amount,
                        note="دفعة كاملة من شاشة الطالب",
                    )
        return instance
