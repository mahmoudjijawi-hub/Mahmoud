"""JWT يتحقق من token_version ومهلة خمول الساعة."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from accounts.idle import enforce_idle_or_touch


class VersionedJWTAuthentication(JWTAuthentication):
    """يرفض توكن مدير إصداره أقدم، ويغلق الجلسة بعد ساعة خمول فقط."""

    def get_header(self, request):
        header = super().get_header(request)
        if header is not None:
            return header
        # بعض واجهات الطالب ترسل التوكن في رأس مستقل
        alt = request.META.get("HTTP_STUDENTTOKEN") or request.META.get("HTTP_STUDENT_TOKEN")
        if not alt:
            return None
        if isinstance(alt, str):
            alt = alt.encode("iso-8859-1")
        prefix = b"StudentToken "
        if alt.lower().startswith(b"studenttoken ") or alt.lower().startswith(b"bearer "):
            return alt
        return prefix + alt

    def get_user(self, validated_token):
        # استخراج المستخدم بالطريقة الافتراضية أولاً
        user = super().get_user(validated_token)
        # قراءة إصدار التوكن من الـ payload إن وُجد
        token_version = validated_token.get("token_version")
        # إن كان المستخدم مديراً نقارن الإصدار
        if user.role == user.ROLE_MANAGER and token_version is not None:
            if int(token_version) != int(user.token_version):
                # توكن قديم بعد دخول جديد من جهاز آخر
                raise InvalidToken("تم إبطال هذه الجلسة لتسجيل دخول أحدث")
        return enforce_idle_or_touch(user)
