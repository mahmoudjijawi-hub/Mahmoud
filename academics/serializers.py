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
        from core.digits import normalize_digits

        value = normalize_digits(value)
        if not str(value).isdigit():
            raise serializers.ValidationError("الرقم المميز يجب أن يكون رقمياً.")
        if len(str(value)) > 10:
            raise serializers.ValidationError("الرقم المميز 10 خانات كحد أقصى.")
        return str(value)

    def validate_teacher_number(self, value):
        from core.digits import normalize_digits

        value = normalize_digits(value)
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
        if special is not None:
            from academics.reclaim import reclaim_special_number

            instance = getattr(self, "instance", None)
            if not reclaim_special_number(
                special,
                role="teacher",
                exclude_teacher_id=getattr(instance, "pk", None),
                exclude_user_id=getattr(getattr(instance, "user", None), "pk", None),
            ):
                raise serializers.ValidationError(
                    {"special_number": f"الرقم المميز {special} مستخدم مسبقاً لحساب نشط."}
                )
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["user"] = str(instance.user_id)
        # شاشة الطالب تستخدم profile_image مع صورة افتراضية إن كانت فارغة
        data["profile_image"] = None
        request = self.context.get("request")
        if instance.cv_file:
            try:
                url = instance.cv_file.url
                data["profile_image"] = (
                    request.build_absolute_uri(url) if request is not None else url
                )
            except ValueError:
                data["profile_image"] = None
        return data

    def _gender_value(self, value):
        # حفظ المدخل كنص ليقبل true و Yes
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value) if value is not None else ""

    @transaction.atomic
    def create(self, validated_data):
        from django.db import IntegrityError
        from academics.reclaim import allocate_username, reclaim_special_number

        validated_data.pop("user", None)
        special = validated_data["special_number"]
        reclaim_special_number(special, role="teacher")
        gender = self._gender_value(validated_data.get("gender", ""))
        request = self.context.get("request")
        cv_file = request.FILES.get("cv") if request is not None else None
        cv_text = validated_data.get("cv", "")
        if cv_file and not cv_text:
            cv_text = cv_file.name[:175]
        try:
            user = CustomUser.objects.create_user(
                username=allocate_username("t", special),
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
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"special_number": f"تعذر إنشاء الأستاذ بالرقم {special} — الرقم مستخدم."}
            ) from exc
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
    address = serializers.CharField(max_length=100)
    personal_notes = serializers.CharField(max_length=100, required=False, allow_blank=True)
    is_payer = FlexibleBooleanField(required=False)
    class1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    class2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    class3 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    subjects = serializers.SerializerMethodField()
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
            "subjects",
            "confirm_special_number",
        )
        read_only_fields = ("id", "subjects")

    def get_subjects(self, instance):
        from academics.subjects import student_subject_names

        return student_subject_names(instance)

    def to_internal_value(self, data):
        from academics.subjects import flatten_class_fields

        # المصفوفات (اختيار مواد متعدد) تُسطَّح قبل CharField
        data, names = flatten_class_fields(data)
        self._incoming_subject_names = names

        if "is_payer" not in data or data.get("is_payer") in (None, ""):
            for key in ("isPayer", "IsPayer", "payer", "paid", "is_paid", "isPaid"):
                if key in data and data.get(key) not in (None, ""):
                    data["is_payer"] = data[key]
                    break
        if "special_number" not in data or data.get("special_number") in (None, ""):
            for key in ("specialNumber", "number", "student_special_number"):
                if key in data and data.get(key) not in (None, ""):
                    data["special_number"] = data[key]
                    break
        if "student_class" not in data or data.get("student_class") in (None, ""):
            for key in ("studentClass", "class_name"):
                if key in data and data.get(key) not in (None, "") and not isinstance(data.get(key), (list, tuple, set)):
                    data["student_class"] = data[key]
                    break
            class_value = data.get("class")
            if class_value not in (None, "") and not isinstance(class_value, (list, tuple, set)):
                data["student_class"] = class_value
        if "parent_number" not in data or data.get("parent_number") in (None, ""):
            for key in ("parentNumber", "parent_phone"):
                if key in data and data.get(key) not in (None, ""):
                    data["parent_number"] = data[key]
                    break
        if "student_number" not in data or data.get("student_number") in (None, ""):
            for key in ("studentNumber", "phone", "student_phone"):
                if key in data and data.get(key) not in (None, ""):
                    data["student_number"] = data[key]
                    break
        if "first_name" not in data or data.get("first_name") in (None, ""):
            for key in ("firstName", "fname"):
                if key in data and data.get(key) not in (None, ""):
                    data["first_name"] = data[key]
                    break
        if "last_name" not in data or data.get("last_name") in (None, ""):
            for key in ("lastName", "lname"):
                if key in data and data.get(key) not in (None, ""):
                    data["last_name"] = data[key]
                    break
        # في PATCH: النصوص الفارغة تفسد التحقق (هواتف...) — نحذفها ليبقى الحقل كما هو
        if getattr(self, "partial", False):
            for key in list(data.keys()):
                if data.get(key) == "":
                    data.pop(key, None)
        return super().to_internal_value(data)

    def validate_special_number(self, value):
        from core.digits import normalize_digits

        value = normalize_digits(value)
        if not str(value).isdigit():
            raise serializers.ValidationError("الرقم المميز يجب أن يكون رقمياً.")
        if len(str(value)) > 10:
            raise serializers.ValidationError("الرقم المميز 10 خانات كحد أقصى.")
        return str(value)

    def _phone(self, value, field_ar):
        from core.digits import normalize_digits

        value = normalize_digits(value)
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
        if special is not None:
            from academics.reclaim import reclaim_special_number

            instance = getattr(self, "instance", None)
            existing = None
            if instance is None:
                existing = Student.objects.filter(special_number=special).select_related("user").first()
            if existing is not None:
                first = str(attrs.get("first_name") or "").strip()
                last = str(attrs.get("last_name") or "").strip()
                same_person = (
                    first
                    and last
                    and first == (existing.first_name or "").strip()
                    and last == (existing.last_name or "").strip()
                )
                if same_person:
                    # نفس الطالب يسجّل مادة إضافية
                    self._merge_existing = existing
                else:
                    raise serializers.ValidationError(
                        {
                            "special_number": (
                                f"الرقم المميز {special} مستخدم لطالب نشط حالياً. "
                                "احذف الطالب القديم أولاً أو اختر رقماً آخر."
                            )
                        }
                    )
            elif not reclaim_special_number(
                special,
                role="student",
                exclude_student_id=getattr(instance, "pk", None),
                exclude_user_id=getattr(getattr(instance, "user", None), "pk", None),
            ):
                raise serializers.ValidationError(
                    {
                        "special_number": (
                            f"الرقم المميز {special} مستخدم لطالب نشط حالياً. "
                            "احذف الطالب القديم أولاً أو اختر رقماً آخر."
                        )
                    }
                )
        return attrs

    def _extract_amount(self, raw):
        from decimal import Decimal, InvalidOperation

        if not isinstance(raw, dict):
            return None
        amount_raw = (
            raw.get("FullAmount")
            or raw.get("full_amount")
            or raw.get("fullAmount")
            or raw.get("amount")
            or raw.get("PaidAmount")
            or raw.get("paid_amount")
            or raw.get("paidAmount")
            or raw.get("total")
        )
        if amount_raw in (None, ""):
            return None
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return amount if amount > 0 else None

    def _record_full_payment(self, student, amount, note="دفعة كاملة من شاشة الطالب"):
        from decimal import Decimal
        from payments.models import Payment, PaymentTransaction

        payment = Payment(
            student=student,
            FullAmount=amount,
            PaidAmount=amount,
            Paymentresult=Decimal("0"),
            payment_type=Payment.TYPE_FULL,
        )
        payment.recalculate()
        payment.save()
        PaymentTransaction.objects.create(payment=payment, amount=amount, note=note)
        return payment

    def _sync_payments_when_payer(self, student, raw):
        """عند is_payer=true: إنشاء/إكمال الدفعات المرتبطة بزر الدفع."""
        from payments.models import Payment, PaymentTransaction

        amount = self._extract_amount(raw)
        open_payments = list(
            Payment.objects.filter(student=student).exclude(Paymentresult=0)
        )
        if amount is not None:
            if open_payments:
                for payment in open_payments:
                    old_paid = payment.PaidAmount
                    payment.PaidAmount = payment.FullAmount
                    payment.recalculate()
                    payment.save()
                    PaymentTransaction.objects.create(
                        payment=payment,
                        amount=payment.PaidAmount - old_paid,
                        note="إكمال دفعة من زر الدفع",
                    )
            else:
                self._record_full_payment(student, amount)
            return

        # بلا مبلغ: أكمل أي دفعات مفتوحة، وإلا اترك is_payer فقط
        for payment in open_payments:
            old_paid = payment.PaidAmount
            payment.PaidAmount = payment.FullAmount
            payment.recalculate()
            payment.save()
            PaymentTransaction.objects.create(
                payment=payment,
                amount=payment.PaidAmount - old_paid,
                note="إكمال دفعة من تعليم is_payer",
            )

    def _incoming_names(self, raw):
        from academics.subjects import collect_subject_names

        names = getattr(self, "_incoming_subject_names", None)
        if names:
            return names
        return collect_subject_names(raw)

    def _raw_has_subject_list(self, raw):
        if not isinstance(raw, dict) and not hasattr(raw, "get"):
            return False
        for key in ("subjects", "subjects_list", "subjectsList", "subject_names", "subjectNames", "classes", "class_list", "classList"):
            if isinstance(raw.get(key), (list, tuple, set)):
                return True
        if isinstance(raw.get("class1"), (list, tuple, set)):
            return True
        if isinstance(raw.get("class"), (list, tuple, set)):
            return True
        return False

    def _sync_subjects(self, student, raw, merging=False):
        from academics.subjects import apply_subjects

        names = self._incoming_names(raw)
        if not names:
            return
        if merging:
            apply_subjects(student, names, merge=True)
            return
        merge = getattr(self, "partial", False) and not self._raw_has_subject_list(raw)
        apply_subjects(student, names, merge=merge)

    @transaction.atomic
    def create(self, validated_data):
        from django.db import IntegrityError
        from academics.reclaim import allocate_username, reclaim_special_number

        special = validated_data["special_number"]
        raw = getattr(self, "initial_data", {}) or {}
        existing = getattr(self, "_merge_existing", None)
        if existing is not None:
            for key in ("class1", "class2", "class3"):
                validated_data.pop(key, None)
            return self.update(existing, validated_data)
        reclaim_special_number(special, role="student")
        try:
            user = CustomUser.objects.create_user(
                username=allocate_username("s", special),
                password=None,
                first_name=validated_data["first_name"],
                last_name=validated_data["last_name"],
                special_number=special,
                role=CustomUser.ROLE_STUDENT,
                user_type="3",
            )
            student = Student.objects.create(user=user, **validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {
                    "special_number": (
                        f"تعذر إضافة الطالب بالرقم {special}. "
                        "الرقم أو اسم المستخدم محجوز — احذف الطالب القديم أو غيّر الرقم."
                    ),
                    "detail": "تعذر إضافة الطالب بسبب تعارض في قاعدة البيانات.",
                }
            ) from exc
        if student.is_payer:
            self._sync_payments_when_payer(student, raw)
        self._sync_subjects(student, raw, merging=False)
        return student

    @transaction.atomic
    def update(self, instance, validated_data):
        raw = getattr(self, "initial_data", {}) or {}
        merging = getattr(self, "_merge_existing", None) is not None and getattr(self, "instance", None) is None
        if merging:
            for key in ("class1", "class2", "class3"):
                validated_data.pop(key, None)
        was_payer = instance.is_payer
        became_payer = (
            "is_payer" in validated_data
            and validated_data.get("is_payer") is True
            and not was_payer
        )
        # زر الدفع قد يرسل مبلغاً مع is_payer=true حتى لو كان مسدداً مسبقاً
        force_pay = validated_data.get("is_payer") is True and self._extract_amount(raw) is not None
        lost_payer = (
            "is_payer" in validated_data
            and validated_data.get("is_payer") is False
            and was_payer
        )
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        user = instance.user
        user.first_name = instance.first_name
        user.last_name = instance.last_name
        user.special_number = instance.special_number
        user.save(update_fields=["first_name", "last_name", "special_number"])

        if became_payer or force_pay:
            self._sync_payments_when_payer(instance, raw)
            if not instance.is_payer:
                instance.is_payer = True
                instance.save(update_fields=["is_payer"])
        if lost_payer:
            from payments.services import reset_student_payments

            reset_student_payments(instance)
        self._sync_subjects(instance, raw, merging=merging)
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["isPayer"] = data.get("is_payer")
        data["specialNumber"] = data.get("special_number")
        subjects = data.get("subjects") or []
        data["classes"] = subjects
        data["subjects_list"] = subjects
        path = student_path_labels(instance)
        data["class1"] = path["class1"]
        data["class2"] = path["class2"]
        data["class3"] = path["class3"]
        # شاشة البرنامج تخزّن الصف/الشعبة من تسجيل الدخول بهذه الأسماء
        data["studentGrade"] = path["class1"]
        data["studentSection"] = path["class3"]
        return data


def student_path_labels(student):
    """class1 المرحلة+الفرع و class3 الشعبة — نفس الشكل في الدخول والبروفايل والبرنامج."""
    level = (getattr(student, "class1", None) or "").strip()
    class2 = (getattr(student, "class2", None) or "").strip()
    class3 = (getattr(student, "class3", None) or "").strip()
    grade_tokens = ("علمي", "أدبي", "عاشر", "تاسع", "ثامن", "سابع")
    class1 = level
    if class2 in grade_tokens and class2 not in level:
        class1 = f"{level} {class2}".strip()
    if not class3 and getattr(student, "section", None) is not None:
        class3 = (student.section.name or "").strip()
    return {"class1": class1, "class2": class2, "class3": class3}
