"""مهلة خمول الجلسة: تُغلق بعد ساعة بلا طلبات، وتتجدد مع كل نشاط."""
from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken

IDLE_MESSAGE = "انتهت الجلسة بسبب الخمول. يرجى تسجيل الدخول مجدداً"


def session_idle_seconds():
    """مدة الخمول بالثواني قبل إغلاق الجلسة."""
    return int(getattr(settings, "SESSION_IDLE_SECONDS", 60 * 60))


def is_session_idle(user, now=None):
    """هل مرّت ساعة دون نشاط منذ last_activity؟"""
    now = now or timezone.now()
    last = getattr(user, "last_activity", None)
    if last is None:
        return False
    return (now - last).total_seconds() > session_idle_seconds()


def touch_activity(user, now=None, min_interval_seconds=30):
    """تحديث آخر نشاط حتى لا تُحتسب الجلسة خاملة أثناء الاستخدام."""
    now = now or timezone.now()
    last = getattr(user, "last_activity", None)
    if last is not None and (now - last).total_seconds() < min_interval_seconds:
        return
    type(user).objects.filter(pk=user.pk).update(last_activity=now)
    user.last_activity = now


def enforce_idle_or_touch(user):
    """رفض التوكن إن خملت الجلسة، وإلا جدّد عداد النشاط."""
    now = timezone.now()
    if is_session_idle(user, now):
        raise InvalidToken(IDLE_MESSAGE)
    touch_activity(user, now)
    return user
