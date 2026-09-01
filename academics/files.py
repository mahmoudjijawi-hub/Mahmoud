"""التحقق من ملفات السيرة الذاتية: الامتداد، البصمة، الحجم، وإعادة التسمية."""
import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible


# البصمات السحرية المسموحة: PDF وصور وZIP/DOCX
_SIGNATURES = (
    (b"%PDF", "application/pdf", ".pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
)


def _sniff(file_obj):
    """قراءة بداية الملف لتحديد النوع الحقيقي وليس الامتداد فقط."""
    # حفظ موضع المؤشر
    current = file_obj.tell()
    # الانتقال لبداية الملف
    file_obj.seek(0)
    # قراءة رأس كافٍ للبصمات
    header = file_obj.read(16)
    # إعادة المؤشر كما كان
    file_obj.seek(current)
    for magic, mime, ext in _SIGNATURES:
        if header.startswith(magic):
            return mime, ext
    return None, None


def validate_cv_file(file_obj):
    """رفض الملفات غير المسموحة أو الأثقل من الحد."""
    if file_obj.size > settings.MAX_CV_UPLOAD_BYTES:
        raise ValidationError("حجم ملف السيرة الذاتية يجب ألا يتجاوز 5 ميغابايت.")
    mime, ext = _sniff(file_obj)
    if mime is None:
        raise ValidationError("يُسمح فقط بملفات PDF أو DOCX أو الصور.")
    name = getattr(file_obj, "name", "") or ""
    # منع path traversal في الاسم الأصلي
    if ".." in name.replace("\\", "/") or name.startswith("/"):
        raise ValidationError("اسم الملف غير صالح.")
    return ext


@deconstructible
class UUIDCVUploadTo:
    """تخزين الملف خارج مجلد عام مباشر باسم UUID."""

    def __call__(self, instance, filename):
        ext = os.path.splitext(filename)[1].lower() or ".bin"
        # اسم جديد غير متوقع
        new_name = f"{uuid.uuid4().hex}{ext}"
        return os.path.join("private", "cvs", new_name)
