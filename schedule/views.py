"""واجهات /api/time_table/ و /api/programs/."""
import re
import uuid

from rest_framework import viewsets
from rest_framework.response import Response

from core.digits import normalize_digits
from core.permissions import IsManagerOrReadOnlyAuthenticated
from schedule.models import TimeTable, Program
from schedule.serializers import (
    TimeTableSerializer,
    ProgramSerializer,
    programs_in_same_slot,
    _normalize_certificate,
)


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


def _fold_ar(value):
    """توحيد الهمزات والمسافات والأرقام لمقارنة الشعبة."""
    text = normalize_digits(str(value or "")).strip()
    text = re.sub(r"\s+", " ", text)
    for alef in "أإآٱ":
        text = text.replace(alef, "ا")
    return text.replace("ى", "ي").replace("ة", "ه").lower()


def _student_section_label(student):
    from academics.serializers import student_path_labels

    return student_path_labels(student)["class3"]


def _sections_equal(left, right):
    folded_left = _fold_ar(left)
    folded_right = _fold_ar(right)
    if not folded_left or not folded_right:
        return False
    return (
        folded_left == folded_right
        or folded_left in folded_right
        or folded_right in folded_left
    )


def _student_path_blob(student):
    from academics.serializers import student_path_labels

    path = student_path_labels(student)
    parts = [path["class1"], path["class2"], getattr(student, "student_class", "")]
    if getattr(student, "stage", None) is not None:
        parts.append(student.stage.name)
    return _fold_ar(" ".join(str(part) for part in parts if part))


_CERT_MARKERS = {
    "baccalaureate": ("بكالوريا", "baccalaureate", "bac"),
    "eleventh": ("حادي عشر", "الحادي عشر", "eleventh"),
    "transitional": ("تاسع", "عاشر", "انتقالي", "transitional"),
}


def _path_compatible(program, student):
    """نفس الشعبة لا تكفي إن كان علمي/أدبي أو بكالوريا/حادي عشر مختلفين."""
    blob = _student_path_blob(student)
    if not blob.strip():
        return True

    grade = _fold_ar(program.grade)
    has_science = "علمي" in blob
    has_literary = "ادبي" in blob
    if grade == "علمي" and has_literary and not has_science:
        return False
    if grade in ("ادبي", "أدبي") and has_science and not has_literary:
        return False

    cert = _normalize_certificate(program.certificate_type)
    markers = _CERT_MARKERS.get(cert, ())
    student_has_cert = any(
        _fold_ar(marker) in blob
        for marks in _CERT_MARKERS.values()
        for marker in marks
    )
    if student_has_cert and markers:
        if not any(_fold_ar(marker) in blob for marker in markers):
            return False
    return True


def _filter_programs_for_student(qs, student):
    """
    شاشة برنامج الطالب: GET /api/programs/?student_id=
    نُظهر حصص شعبة الطالب فقط — بدون إعادة الجدول كاملاً إن لم يوجد تطابق.
    """
    section = _student_section_label(student)
    if not section:
        return qs.none()

    matched_ids = [
        program.pk
        for program in qs
        if _sections_equal(program.section, section) and _path_compatible(program, student)
    ]
    return qs.filter(pk__in=matched_ids)


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

    def paginate_queryset(self, queryset):
        params = self.request.query_params
        if params.get("page") or params.get("page_size"):
            return super().paginate_queryset(queryset)
        return None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["student"] = self._target_student()
        return context

    def _target_student(self):
        user = self.request.user
        if getattr(user, "role", None) == "student":
            return getattr(user, "student_profile", None)
        student_ref = (
            self.request.query_params.get("student_id")
            or self.request.query_params.get("studentId")
            or self.request.query_params.get("student")
        )
        if student_ref:
            return _resolve_student_ref(student_ref)
        return None

    def list(self, request, *args, **kwargs):
        """شاشة حضور الطالب: GET /api/time_table/?student_id= مصفوفة Date/Status/subject."""
        student = self._target_student()
        if student is not None:
            return Response(self._student_attendance_log(student))
        return super().list(request, *args, **kwargs)

    def _student_attendance_log(self, student):
        from attendance.models import Attendance
        from attendance.serializers import _attendance_subject
        from attendance.views import _sync_attendance_from_timetable
        from schedule.serializers import _arabic_subject

        _sync_attendance_from_timetable(student)
        lessons = list(
            TimeTable.objects.filter(student=student)
            .select_related("Teacher")
            .prefetch_related("student")
            .order_by("-Day", "-Hour")
        )
        serializer = self.get_serializer(lessons, many=True)
        rows = list(serializer.data)
        seen = {
            (str(row.get("Date") or row.get("Day") or ""), _arabic_subject(row.get("subject")))
            for row in rows
        }

        extras = Attendance.objects.filter(student=student).order_by("-Date", "subject")
        for record in extras:
            day = record.Date.isoformat() if hasattr(record.Date, "isoformat") else str(record.Date)
            subject = _arabic_subject(_attendance_subject(record))
            if (day, subject) in seen:
                continue
            rows.append(
                {
                    "id": str(record.id),
                    "Day": day,
                    "day": day,
                    "date": day,
                    "Date": day,
                    "session_date": day,
                    "Subject": subject,
                    "subject": subject,
                    "subject_name": subject,
                    "Status": record.Status,
                    "status": record.Status,
                    "attendance_status": record.Status,
                    "is_present": record.Status == Attendance.STATUS_PRESENT,
                }
            )
            seen.add((day, subject))

        rows.sort(
            key=lambda row: (str(row.get("Date") or ""), str(row.get("subject") or "")),
            reverse=True,
        )
        return rows

    def get_queryset(self):
        qs = TimeTable.objects.select_related("Teacher").prefetch_related("student").all()
        user = self.request.user
        student = self._target_student()
        if user.role == "student":
            if student is None:
                return qs.none()
            return qs.filter(student=student).distinct()
        if student is not None:
            return qs.filter(student=student).distinct()
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["student"] = self._target_student()
        return context

    def _target_student(self):
        user = self.request.user
        params = self.request.query_params
        if getattr(user, "role", None) == "student":
            return getattr(user, "student_profile", None)
        student_ref = (
            params.get("student_id")
            or params.get("studentId")
            or params.get("student")
        )
        if student_ref:
            return _resolve_student_ref(student_ref)
        return None

    def get_queryset(self):
        qs = Program.objects.select_related("teacher_name").all()
        user = self.request.user
        params = self.request.query_params
        if user.role == "teacher":
            qs = qs.filter(teacher_name__user=user)

        target_student = self._target_student()
        if user.role == "student" and target_student is None:
            return qs.none()
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

    def perform_destroy(self, instance):
        """حذف الخلية كلها: 8 و 8:00 و 08:00 لنفس الأحد تُزال معاً."""
        siblings = programs_in_same_slot(instance)
        if not siblings:
            instance.delete()
            return
        for program in siblings:
            program.delete()

    def _destroy_if_subject_cleared(self, request):
        data = getattr(request, "data", {}) or {}
        subject = data.get("subject_name") if hasattr(data, "get") else None
        if subject is None or str(subject).strip() != "":
            return None
        self.perform_destroy(self.get_object())
        return Response(status=204)

    def update(self, request, *args, **kwargs):
        cleared = self._destroy_if_subject_cleared(request)
        if cleared is not None:
            return cleared
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        cleared = self._destroy_if_subject_cleared(request)
        if cleared is not None:
            return cleared
        return super().partial_update(request, *args, **kwargs)
