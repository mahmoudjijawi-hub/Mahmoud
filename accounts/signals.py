"""إشارات حفظ آخر جلسة للمدير عند دخول Django Admin."""
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.sessions.models import Session

from accounts.models import CustomUser, LoginLog


def _client_ip(request):
    """استخراج IP مع الحذر من رؤوس الوكيل: نأخذ REMOTE_ADDR فقط."""
    # لا نثق بـ X-Forwarded-For هنا لتفادي التزييف ما لم يضبط nginx ذلك لاحقاً
    return request.META.get("REMOTE_ADDR")


@receiver(user_logged_in)
def on_manager_session_login(sender, request, user, **kwargs):
    """عند دخول مدير عبر الجلسة: أبطل الجلسات الأخرى وسجّل العملية."""
    # نتجاهل غير المديرين
    if not isinstance(user, CustomUser) or user.role != CustomUser.ROLE_MANAGER:
        return
    # ضمان وجود مفتاح جلسة
    if not request.session.session_key:
        request.session.save()
    new_key = request.session.session_key
    # حذف كل جلسات Django الأخرى المرتبطة بهذا المستخدم
    for session in Session.objects.exclude(session_key=new_key):
        data = session.get_decoded()
        # مفتاح المستخدم في الجلسة هو _auth_user_id كنص UUID
        if str(data.get("_auth_user_id")) == str(user.pk):
            session.delete()
    # تخزين المفتاح الصالح الوحيد
    user.last_session_key = new_key or ""
    user.save(update_fields=["last_session_key"])
    # كتابة سجل تدقيق بدون كلمة مرور أو رقم مميز
    LoginLog.objects.create(
        user=user,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
    )
