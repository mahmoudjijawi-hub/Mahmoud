"""تسجيل نموذج الاشتراك في لوحة الإدارة."""
from django.contrib import admin

from core.models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    # عرض تاريخ الانتهاء وحالة التفعيل بوضوح
    list_display = ("expiry_date", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
