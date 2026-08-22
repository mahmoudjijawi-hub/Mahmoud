"""واجهات الأساتذة والطلاب المطابقة للـ Collection مع منع IDOR."""
import uuid

from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from academics.models import Teacher, Student
from academics.serializers import TeacherSerializer, StudentSerializer, StudentPagination
from core.permissions import IsManagerOrReadOnlyAuthenticated, IsStudentOwner


def _is_uuid(value):
    """هل القيمة UUID صالح لمفتاح الطالب؟"""
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


class TeacherViewSet(viewsets.ModelViewSet):
    """GET/POST /api/teachers/ و PATCH /api/teachers/{uuid}/"""

    serializer_class = TeacherSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    queryset = Teacher.objects.select_related("user").all()
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def perform_destroy(self, instance):
        """حذف نهائي للأستاذ وحسابه حتى يتحرر الرقم المميز."""
        from django.db import transaction

        user = instance.user
        with transaction.atomic():
            instance.delete()
            if user is not None and getattr(user, "pk", None):
                type(user).objects.filter(pk=user.pk).delete()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # الأستاذ يرى ملفه فقط
        if user.role == "teacher":
            return qs.filter(user=user)
        # الطالب لا يرى قائمة الأساتذة كاملة — يُصفَّى عبر البرامج لاحقاً
        if user.role == "student":
            return qs.none()
        teacher_id = self.request.query_params.get("teacher_id")
        if teacher_id:
            qs = qs.filter(pk=teacher_id)
        return qs

    @action(detail=True, methods=["get"], url_path="cv")
    def download_cv(self, request, pk=None):
        """تنزيل ملف السيرة عبر مسار محمي بدل رابط ثابت عام."""
        teacher = self.get_object()
        if request.user.role != "manager":
            return Response({"detail": "غير مصرح."}, status=status.HTTP_403_FORBIDDEN)
        if not teacher.cv_file:
            raise Http404("لا يوجد ملف سيرة ذاتية.")
        return FileResponse(teacher.cv_file.open("rb"), as_attachment=True)


class StudentViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/students/
    PATCH/DELETE /api/students/{uuid}/ أو /api/students/{special_number}/
    البحث بـ special_number أو name/search مع ترقيم الصفحات.
    """

    serializer_class = StudentSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated, IsStudentOwner)
    pagination_class = StudentPagination
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def paginate_queryset(self, queryset):
        """
        الواجهة تتوقع مصفوفة مباشرة: searchResponse.data.length و students.map
        لا نُرقّم إلا إذا طُلب page أو page_size صراحة.
        """
        params = self.request.query_params
        if params.get("page") or params.get("page_size"):
            return super().paginate_queryset(queryset)
        return None

    def get_serializer(self, *args, **kwargs):
        # PUT من زر التصفير يرسل حقولاً ناقصة؛ نعامل التحديث كجزئي دائماً
        if self.action in ("update", "partial_update"):
            kwargs["partial"] = True
        return super().get_serializer(*args, **kwargs)

    def get_queryset(self):
        # لا يوجد شطب ناعم: الحذف نهائي، فكل سجل موجود هو سجل فعّال
        qs = Student.objects.select_related("user").order_by(
            "first_name", "last_name", "special_number"
        )
        user = self.request.user
        # الطالب يرى ملفه فقط ولا يستخدم فلاتر البحث العامة
        if user.role == "student":
            return qs.filter(user=user)

        params = self.request.query_params
        # كل الأسماء المحتملة التي قد يرسلها الفرونت
        special = (
            params.get("special_number")
            or params.get("specialNumber")
            or params.get("special-number")
            or params.get("number")
            or params.get("student_special_number")
        )
        term = (
            params.get("search")
            or params.get("name")
            or params.get("q")
            or params.get("query")
            or params.get("keyword")
        )

        from core.digits import normalize_digits

        if special is not None and str(special).strip() != "":
            special = normalize_digits(str(special).strip())
            qs = qs.filter(special_number=special)

        if term is not None and str(term).strip() != "":
            term = normalize_digits(str(term).strip())
            if term.isdigit():
                # الواجهة تستخدم ?search=الرقم المميز وتتوقع الطالب نفسه لا أرقاماً جزئية
                exact = qs.filter(special_number=term)
                if exact.exists():
                    qs = exact
                else:
                    qs = qs.filter(
                        Q(special_number__icontains=term)
                        | Q(first_name__icontains=term)
                        | Q(last_name__icontains=term)
                    )
            else:
                qs = qs.filter(
                    Q(first_name__icontains=term)
                    | Q(last_name__icontains=term)
                    | Q(special_number__icontains=term)
                )

        return qs

    def get_object(self):
        """
        يدعم الجلب بالـ UUID أو بالرقم المميز مباشرة:
        GET /api/students/22/  → نفس نتيجة البحث بالرقم 22
        """
        lookup = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        queryset = self.filter_queryset(self.get_queryset())

        # إن لم يكن UUID نعتبره رقماً مميزاً
        if lookup and not _is_uuid(lookup):
            obj = get_object_or_404(queryset, special_number=str(lookup).strip())
            self.check_object_permissions(self.request, obj)
            return obj

        return super().get_object()

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        """
        مسار صريح للبحث: GET /api/students/search/?special_number=22
        أو GET /api/students/search/?q=22
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post", "put", "patch"], url_path="pay")
    def pay(self, request, pk=None):
        """
        زر الدفع من بطاقة الطالب:
        POST /api/students/{id|special_number}/pay/
        """
        from payments.services import execute_payment, extract_raw_payload
        from rest_framework.exceptions import ValidationError

        student = self.get_object()
        payload = extract_raw_payload(request)
        payload["student"] = str(student.id)
        payload["special_number"] = student.special_number
        payload.setdefault("payment_type", "full")
        try:
            payment, data = execute_payment(payload, force_full=True)
        except ValidationError as exc:
            return Response(
                {
                    "success": False,
                    "detail": "تعذر إتمام الدفع من بطاقة الطالب.",
                    "errors": exc.detail,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        student.refresh_from_db()
        data["student_is_payer"] = student.is_payer
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post", "put", "patch"], url_path="full-payment")
    def full_payment(self, request, pk=None):
        """مرادف: POST /api/students/{id}/full-payment/"""
        return self.pay(request, pk=pk)

    @action(detail=True, methods=["post", "put", "patch"], url_path="confirm-payment")
    def confirm_payment(self, request, pk=None):
        """
        زر الدفعة الكاملة في الواجهة:
        POST /api/students/{id}/confirm-payment/
        الجسم فارغ — نعلّم الطالب مسدداً ونُكمل أي قسط مفتوح.
        """
        from rest_framework.exceptions import ValidationError

        from payments.services import execute_payment

        student = self.get_object()
        payload = {
            "student": str(student.id),
            "special_number": student.special_number,
            "payment_type": "full",
        }
        try:
            _payment, data = execute_payment(payload, force_full=True)
        except ValidationError:
            # لا قسط مسجّل: يكفي تعليم is_payer كما تتوقع الواجهة
            if not student.is_payer:
                student.is_payer = True
                student.save(update_fields=["is_payer"])
            data = {
                "success": True,
                "message": "تم تأكيد الدفع",
                "detail": "تم تأكيد الدفع",
                "first_name": student.first_name,
                "last_name": student.last_name,
                "special_number": student.special_number,
                "is_payer": True,
                "student_is_payer": True,
            }
            student.refresh_from_db()
            return Response(data, status=status.HTTP_200_OK)
        student.refresh_from_db()
        if not student.is_payer:
            student.is_payer = True
            student.save(update_fields=["is_payer"])
        data["student_is_payer"] = True
        data["first_name"] = student.first_name
        data["last_name"] = student.last_name
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post", "put", "patch"], url_path="reset-all-payments")
    def reset_all_payments(self, request):
        """تصفير دفعة كل الطلاب دفعة واحدة بدل N طلبات PUT."""
        from payments.services import reset_student_payments

        count = 0
        for student in self.get_queryset():
            reset_student_payments(student)
            count += 1
        return Response(
            {
                "success": True,
                "message": "تم تصفير الدفع لجميع الطلاب",
                "detail": "تم تصفير الدفع لجميع الطلاب",
                "reset_students": count,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="payments")
    def payments(self, request, pk=None):
        """
        بيانات الطالب ومدفوعاته:
        GET /api/students/{id|رقم مميز}/payments/
        """
        from payments.services import student_payment_summary

        student = self.get_object()
        return Response(student_payment_summary(student), status=status.HTTP_200_OK)

    @action(detail=True, methods=["post", "put", "patch"], url_path="reset-payment")
    def reset_payment(self, request, pk=None):
        """زر تصفير الدفع من بطاقة الطالب."""
        from payments.services import reset_student_payments

        student = self.get_object()
        return Response(reset_student_payments(student), status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        """
        حذف نهائي من قاعدة البيانات: الطالب + حساب المستخدم + السجلات التابعة.
        الرقم المميز واسم المستخدم يتحرران فوراً لإعادة الاستخدام.
        """
        from django.db import transaction

        user = instance.user
        with transaction.atomic():
            instance.delete()
            if user is not None and getattr(user, "pk", None):
                # حذف الحساب حتى لا يبقى username/special_number محجوزاً
                type(user).objects.filter(pk=user.pk).delete()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
