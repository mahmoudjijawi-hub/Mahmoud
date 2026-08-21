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
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

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

    def get_queryset(self):
        # الشطب الناعم: نخفي غير النشطين من القوائم
        qs = Student.objects.select_related("user").filter(is_active=True).order_by(
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

        if special is not None and str(special).strip() != "":
            special = str(special).strip()
            qs = qs.filter(special_number=special)

        if term is not None and str(term).strip() != "":
            term = str(term).strip()
            if term.isdigit():
                # بحث رقمي = رقم مميز (تطابق تام أو جزئي) مع إمكانية الاسم
                qs = qs.filter(
                    Q(special_number=term)
                    | Q(special_number__icontains=term)
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
        يقبل FullAmount / PaidAmount / payment_type مثل /api/payments/
        """
        from payments.serializers import PaymentSerializer

        student = self.get_object()
        payload = {}
        if hasattr(request.data, "items"):
            payload.update({k: v for k, v in request.data.items()})
        for key, value in request.query_params.items():
            if key not in payload or payload.get(key) in (None, ""):
                payload[key] = value
        payload.setdefault("student", str(student.id))
        payload.setdefault("special_number", student.special_number)
        if not payload.get("payment_type"):
            payload["payment_type"] = "full"
        serializer = PaymentSerializer(data=payload)
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "detail": "تعذر إتمام الدفع من بطاقة الطالب.",
                    "errors": serializer.errors,
                    **serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment = serializer.save()
        student.refresh_from_db()
        out = PaymentSerializer(payment).data
        out["student_is_payer"] = student.is_payer
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post", "put", "patch"], url_path="full-payment")
    def full_payment(self, request, pk=None):
        """مرادف: POST /api/students/{id}/full-payment/"""
        return self.pay(request, pk=pk)

    def perform_destroy(self, instance):
        """
        شطب ناعم مع تحرير الرقم المميز واسم المستخدم،
        حتى يمكن إضافة طالب جديد بنفس الرقم (مثل 22) لاحقاً مع بقاء السجلات التاريخية.
        """
        # قيمة فريدة بطول 10 لتفريغ قيد unique على special_number
        released = uuid.uuid4().hex[:10]
        instance.is_active = False
        instance.special_number = released
        instance.save(update_fields=["is_active", "special_number"])
        user = instance.user
        user.is_active = False
        user.special_number = released
        # تحرير username أيضاً لأن الإنشاء يستخدم s{special_number}
        user.username = f"d{released}"[:25]
        user.save(update_fields=["is_active", "special_number", "username"])

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
