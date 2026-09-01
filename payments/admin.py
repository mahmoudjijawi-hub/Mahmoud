from django.contrib import admin

from payments.models import Payment, PaymentTransaction


class PaymentTransactionInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    readonly_fields = ("amount", "note", "created_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("student", "FullAmount", "PaidAmount", "Paymentresult", "status")
    list_filter = ("status", "payment_type")
    inlines = (PaymentTransactionInline,)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("payment", "amount", "note", "created_at")
