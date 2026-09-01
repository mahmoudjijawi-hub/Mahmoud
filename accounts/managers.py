"""مدير إنشاء المستخدمين المخصصين."""
from django.contrib.auth.models import BaseUserManager


class CustomUserManager(BaseUserManager):
    """إنشاء مستخدم عادي أو superuser بدون بريد إلزامي."""

    def create_user(self, username, password=None, **extra_fields):
        # اسم المستخدم إلزامي لأنه حقل USERNAME_FIELD
        if not username:
            raise ValueError("اسم المستخدم مطلوب")
        # تطبيع اسم المستخدم لحساسية أقل للفوارق الشكلية
        username = self.model.normalize_username(username)
        # بناء الكائن دون حفظ أولاً لتعيين كلمة المرور بشكل آمن
        user = self.model(username=username, **extra_fields)
        if password:
            # تجزئة كلمة المرور بـ Argon2 حسب PASSWORD_HASHERS
            user.set_password(password)
        else:
            # الأساتذة والطلاب يدخلون بالرقم المميز بلا كلمة مرور
            user.set_unusable_password()
        # حفظ السجل في قاعدة البيانات
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        # حساب لوحة /admin/ منفصل عن مدير المعهد العادي
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "manager")
        extra_fields.setdefault("user_type", "1")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("يجب أن يكون is_staff=True للمشرف")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("يجب أن يكون is_superuser=True للمشرف")
        return self.create_user(username, password, **extra_fields)
