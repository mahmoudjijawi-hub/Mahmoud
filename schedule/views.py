"""واجهات /api/time_table/ و /api/programs/."""
import uuid

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.response import Response

from core.permissions import IsManagerOrReadOnlyAuthenticated
from schedule.models import TimeTable, Program
from schedule.serializers import TimeTableSerializer, ProgramSerializer


def _is_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _resolve_student_ref(value):
    """قبول UUID الطالب أو الحساب أو الرقم المميز."""
    from academics.models import Student
    from core.digits import normalize_digits

    text = normalize_digits(str(value or "").strip())
    if not text:
        return None
    if _is_uuid(text):
        return (
            Student.objects.filter(pk=text).select_related("stage", "section").first()
            or Student.objects.filter(user_id=text).select_related("stage", "section").first()
        )
    return Student.objects.filter(special_number=text).select_related("stage", "section").first()


def _student_program_tokens(student):
    """كلمات مسار الطالب لمطابقتها مع حقول البرنامج."""
    from academics.subjects import student_subject_names

    tokens = list(student_subject_names(student))
    for raw in (student.class1, student.class2, student.class3, student.student_class):
        if not raw:
            continue
        tokens.extend(
            part.strip()
            for part in str(raw).replace("،", ",").split(",")
            if part.strip()
        )
    if getattr(student, "stage", None) is not None:
        tokens.append(student.stage.name)
    if getattr(student, "section", None) is not None:
        tokens.append(student.section.name)
    seen = set()
    unique = []
    for token in tokens:
        key = token.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(token.strip())
    return unique


def _filter_programs_for_student(qs, student):
    """
    شاشة برنامج الطالب: GET /api/programs/?student_id=
    نطابق المادة/الصف/الشعبة، وإن لم يطابق شيء نعيد الجدول كاملاً حتى لا تبقى الصفحة فارغة.
    """
    tokens = _student_program_tokens(student)
    if not tokens:
        return qs
    query = Q()
    for token in tokens:
        query |= (
            Q(subject_name__iexact=token)
            | Q(subject_name__icontains=token)
            | Q(grade__iexact=token)
            | Q(grade__icontains=token)
            | Q(section__iexact=token)
            | Q(section__icontains=token)
            | Q(certificate_type__iexact=token)
            | Q(certificate_type__icontains=token)
        )
    filtered = qs.filter(query).distinct()
    return filtered if filtered.exists() else qs


def _dedupe_program_slots(qs):
    """حصة واحدة لكل يوم/ساعة/شعبة — الأحدث يبقى حتى يطابق الجدول بعد التعديل."""
    from schedule.serializers import _normalize_time_slot, _arabic_weekday, _normalize_certificate

    seen = {}
    ordered = []
    for program in qs.order_by("id"):
        key = (
            _normalize_certificate(program.certificate_type),
            (program.grade or "").strip(),
            (program.section or "").strip(),
            _arabic_weekday(program.day),
            _normalize_time_slot(program.time_slot),
        )
        if key in seen:
            seen[key] = program
            continue
        seen[key] = program
        ordered.append(key)
    return [seen[key] for key in ordered]


class TimeTableViewSet(viewsets.ModelViewSet):
    serializer_class = TimeTableSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = TimeTable.objects.select_related("Teacher").prefetch_related("student").all()
        user = self.request.user
        if user.role == "student":
            return qs.filter(student__user=user).distinct()
        if user.role == "teacher":
            return qs.filter(Teacher__user=user)
        teacher_id = self.request.query_params.get("teacher_id")
        if teacher_id:
            qs = qs.filter(Teacher_id=teacher_id)
        return qs


class ProgramViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = (IsManagerOrReadOnlyAuthenticated,)
    http_method_names = ["get", "post", "patch", "put", "delete", "head", "options"]

    def paginate_queryset(self, queryset):
        params = self.request.query_params
        if params.get("page") or params.get("page_size"):
            return super().paginate_queryset(queryset)
        return None

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        if getattr(request.user, "role", None) == "manager":
            queryset = _dedupe_program_slots(queryset)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(list(queryset), many=True)
        return Response(serializer.data)

    def get_queryset(self):
        qs = Program.objects.select_related("teacher_name").all()
        user = self.request.user
        params = self.request.query_params
        if user.role == "teacher":
            qs = qs.filter(teacher_name__user=user)

        student_ref = (
            params.get("student_id")
            or params.get("studentId")
            or params.get("student")
        )
        target_student = None
        if user.role == "student":
            target_student = getattr(user, "student_profile", None)
            if target_student is None:
                return qs.none()
            # الطالب يرى جدوله فقط حتى لو أرسل معرّف طالب آخر
        elif student_ref:
            target_student = _resolve_student_ref(student_ref)

        if target_student is not None:
            qs = _filter_programs_for_student(qs, target_student)

        for key in ("certificate_type", "grade", "section", "day", "time_slot", "room", "subject_name"):
            value = params.get(key)
            if value:
                qs = qs.filter(**{key: value})
        teacher_name = params.get("teacher_name") or params.get("teacher_id")
        if teacher_name:
            qs = qs.filter(teacher_name_id=teacher_name)
        return qs
