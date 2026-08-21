"""محللات مرنة لجسم طلب الدفع — الفرونت أحياناً يرسل JSON بدون application/json."""
import json

from rest_framework.parsers import BaseParser, FormParser, JSONParser, MultiPartParser


class LenientJSONParser(JSONParser):
    """يقبل application/json وأي نوع فرعي json."""

    media_type = "application/json"


class PlainTextJSONParser(BaseParser):
    """
    بعض الواجهات ترسل JSON مع Content-Type: text/plain أو بدون نوع.
    بدون هذا يبقى request.data فارغاً ويفشل زر الدفع.
    """

    media_type = "text/plain"

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read()
        if not raw:
            return {}
        encoding = "utf-8"
        if parser_context:
            encoding = parser_context.get("encoding") or "utf-8"
        try:
            text = raw.decode(encoding)
        except Exception:
            text = raw.decode("utf-8", errors="ignore")
        text = (text or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}


PAYMENT_PARSERS = (LenientJSONParser, PlainTextJSONParser, FormParser, MultiPartParser)
