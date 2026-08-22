"""تطبيع الأرقام العربية/الفارسية إلى أرقام لاتينية."""

# أرقام عربية شرقية + فارسية
_DIGIT_TABLE = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)


def normalize_digits(value):
    """تحويل أي أرقام عربية/فارسية إلى 0-9 مع strip."""
    if value is None:
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(int(value)) if isinstance(value, float) and float(value).is_integer() else str(value)
    text = str(value).translate(_DIGIT_TABLE).strip()
    return text
