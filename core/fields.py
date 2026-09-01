"""حقول Serializer مساعدة لمطابقة أجسام الـ Collection (أرقام أو نصوص)."""
from rest_framework import serializers

from core.digits import normalize_digits


class FlexibleCharField(serializers.CharField):
    """يقبل رقماً أو نصاً ويخزّنه كنص — كما في special_number داخل الـ Collection."""

    def to_internal_value(self, data):
        # تحويل الأعداد إلى نص قبل التحقق من الطول
        if data is None:
            return super().to_internal_value(data)
        if isinstance(data, bool):
            # لا نحول boolean هنا حتى لا يصبح "True"
            return super().to_internal_value(data)
        # تطبيع الأرقام العربية (١،٢،٣) إلى لاتينية قبل أي تحقق
        data = normalize_digits(data)
        return super().to_internal_value(data)


class GenderField(serializers.Field):
    """يقبل true أو Yes كما في POST/PATCH الأستاذ داخل الـ Collection."""

    def to_internal_value(self, data):
        if data in (True, False):
            return "true" if data else "false"
        if data is None:
            return ""
        text = str(data).strip()
        lowered = text.lower()
        if lowered in ("true", "1", "yes", "y"):
            return "true"
        if lowered in ("false", "0", "no", "n"):
            return "false"
        return text[:10]

    def to_representation(self, value):
        if value == "true":
            return True
        if value == "false":
            return False
        return value or ""


class FlexibleBooleanField(serializers.Field):
    """يقبل true/false أو Yes/No كما في حقل is_payer داخل الـ Collection."""

    def to_internal_value(self, data):
        if data in (True, False):
            return data
        if data is None or data == "":
            return False
        text = str(data).strip().lower()
        if text in ("true", "1", "yes", "y", "نعم", "صح", "مسدد", "دفع", "full"):
            return True
        if text in ("false", "0", "no", "n", "لا", "غير مسدد"):
            return False
        raise serializers.ValidationError("قيمة غير صالحة للحقل المنطقي.")

    def to_representation(self, value):
        return bool(value)
