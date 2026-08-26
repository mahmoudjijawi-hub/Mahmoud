"""استخراج مواد الطالب من أجسام الواجهة وربطها بسجل Subject."""
import uuid

from academics.models import Subject

_SUBJECT_LIST_KEYS = (
    "subjects",
    "subjects_list",
    "subjectsList",
    "subject_names",
    "subjectNames",
    "classes",
    "class_list",
    "classList",
    "courses",
    "materials",
    "مواد",
)


def _split_names(value):
    """تحويل قيمة واحدة أو قائمة أو نص مفصول بفاصلة إلى أسماء مواد."""
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        names = []
        for item in value:
            names.extend(_split_names(item))
        return names
    text = str(value).strip()
    if not text:
        return []
    if "," in text or "،" in text:
        return [part.strip() for part in text.replace("،", ",").split(",") if part.strip()]
    return [text]


def collect_subject_names(data):
    """
    جمع أسماء المواد من كل الأشكال الشائعة:
    subjects / classes كمصفوفة، class1 قائمة، أو class1+class2+class3 نصوصاً.
    """
    if data is None:
        return []
    if hasattr(data, "items"):
        raw = {k: v for k, v in data.items()}
    else:
        raw = dict(data or {})

    names = []
    if hasattr(data, "getlist"):
        for key in _SUBJECT_LIST_KEYS + ("class1", "class2", "class3", "subject", "class"):
            values = data.getlist(key)
            if len(values) > 1:
                names.extend(_split_names(values))

    for key in _SUBJECT_LIST_KEYS:
        if key in raw:
            names.extend(_split_names(raw.get(key)))

    for key in ("subject", "Subject", "المادة"):
        if key in raw:
            names.extend(_split_names(raw.get(key)))

    # class كمصفوفة = مواد، كنص رقمي = صف دراسي
    class_value = raw.get("class")
    if isinstance(class_value, (list, tuple, set)):
        names.extend(_split_names(class_value))

    # class1 نص المرحلة/الفرع — لا نعتبره مواد
    # class2 في شاشة التعديل = المواد مفصولة بفاصلة عربية
    class2 = raw.get("class2")
    if isinstance(class2, str) and ("،" in class2 or "," in class2):
        names.extend(_split_names(class2))
    elif isinstance(class2, (list, tuple, set)):
        names.extend(_split_names(class2))

    for key in ("class1", "class3"):
        value = raw.get(key)
        if isinstance(value, (list, tuple, set)):
            names.extend(_split_names(value))

    seen = set()
    unique = []
    for name in names:
        text = str(name).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def flatten_class_fields(data):
    """
    إن وصلت class1/class2/class3 أو class كمصفوفة نحوّلها إلى نصوص
    حتى لا يفشل CharField بـ Not a valid string.
    """
    if data is None:
        return {}, []
    if hasattr(data, "items"):
        raw = {k: v for k, v in data.items()}
    else:
        raw = dict(data or {})

    names = collect_subject_names(data)

    if isinstance(raw.get("class"), (list, tuple, set)):
        raw.pop("class", None)

    for key in ("class1", "class2", "class3"):
        if isinstance(raw.get(key), (list, tuple, set)):
            raw[key] = ""

    return raw, names


def resolve_subjects(names):
    """إيجاد أو إنشاء سجلات Subject من أسماء أو UUID."""
    objects = []
    seen_ids = set()
    for raw in names:
        text = str(raw).strip()
        if not text:
            continue
        subject = None
        try:
            subject = Subject.objects.filter(pk=uuid.UUID(text)).first()
        except (TypeError, ValueError, AttributeError):
            subject = None
        if subject is None:
            subject, _ = Subject.objects.get_or_create(name=text[:30])
        if subject.id in seen_ids:
            continue
        seen_ids.add(subject.id)
        objects.append(subject)
    return objects


def student_subject_names(student):
    """أسماء مواد الطالب من العلاقة المتعددة فقط (class1/2/3 للمسار)."""
    return list(student.subjects.values_list("name", flat=True))


def apply_subjects(student, names, merge=True):
    """ربط المواد بالطالب دون الكتابة فوق مسار المرحلة/الصف/الشعبة."""
    incoming = resolve_subjects(names)
    incoming_names = [subject.name for subject in incoming]
    if merge:
        combined = student_subject_names(student)
        for name in incoming_names:
            if name not in combined:
                combined.append(name)
    else:
        combined = incoming_names

    student.subjects.set(resolve_subjects(combined))
    return combined
