"""JWT يتحقق من token_version ومهلة خمول الساعة."""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from accounts.idle import enforce_idle_or_touch


class VersionedJWTAuthentication(JWTAuthentication):
    """يرفض توكن مدير إصداره أقدم، ويغلق الجلسة بعد ساعة خمول فقط."""

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
