"""لوحة إدارة الحسابات وسجلات الدخول."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.models import CustomUser, Manager, LoginLog


@admin.register(CustomUser)
class CustomUserAdmin(DjangoUserAdmin):
    list_display = ("username", "special_number", "role", "is_active", "is_superuser")
    list_filter = ("role", "is_active", "is_superuser")
    search_fields = ("username", "special_number", "first_name", "last_name")
    ordering = ("username",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("البيانات", {"fields": ("first_name", "last_name", "special_number", "role", "user_type")}),
        ("الصلاحيات", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("الجلسة", {"fields": ("last_session_key", "last_activity", "token_version")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "special_number", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "special_number", "user")
    search_fields = ("special_number", "first_name", "last_name")


@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "ip_address", "user_agent")
    list_filter = ("created_at",)
    search_fields = ("user__username", "ip_address")
    readonly_fields = ("user", "created_at", "ip_address", "user_agent")
