"""مسلسل الدفعات بأسماء الحقول كما في الـ Collection."""
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from academics.models import Student
from payments.models import Payment, PaymentTransaction


class PaymentSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.filter(is_active=True))
    FullAmount = serializers.DecimalField(max_digits=12, decimal_places=2)
    PaidAmount = serializers.DecimalField(max_digits=12, decimal_places=2)
    Paymentresult = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
    )

    class Meta:
        model = Payment
        fields = ("id", "student", "FullAmount", "PaidAmount", "Paymentresult")
        read_only_fields = ("id",)

    def validate(self, attrs):
        full_amount = attrs.get("FullAmount")
        paid_amount = attrs.get("PaidAmount")
        if full_amount is not None and paid_amount is not None and paid_amount > full_amount:
            raise serializers.ValidationError("المبلغ المدفوع لا يجوز أن يتجاوز القسط الكلي.")
        return attrs

    def _apply_amounts(self, instance, validated_data):
        if "Paymentresult" not in validated_data or validated_data.get("Paymentresult") is None:
            full_amount = validated_data.get("FullAmount", instance.FullAmount)
            paid_amount = validated_data.get("PaidAmount", instance.PaidAmount)
            validated_data["Paymentresult"] = Decimal(full_amount) - Decimal(paid_amount)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.recalculate()
        instance.save()
        return instance

    @transaction.atomic
    def create(self, validated_data):
        payment = Payment(
            student=validated_data["student"],
            FullAmount=validated_data["FullAmount"],
            PaidAmount=validated_data["PaidAmount"],
            Paymentresult=validated_data.get("Paymentresult") or Decimal("0"),
        )
        payment.recalculate()
        payment.save()
        PaymentTransaction.objects.create(
            payment=payment,
            amount=payment.PaidAmount,
            note="إنشاء دفعة",
        )
        return payment

    @transaction.atomic
    def update(self, instance, validated_data):
        old_paid = instance.PaidAmount
        instance = self._apply_amounts(instance, validated_data)
        delta = instance.PaidAmount - old_paid
        PaymentTransaction.objects.create(
            payment=instance,
            amount=delta,
            note="تعديل دفعة",
        )
        return instance
