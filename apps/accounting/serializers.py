from rest_framework import serializers

from .models import Account


class AccountCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "account_type",
            "account_number",
            "opening_balance",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if "hospital_id" in self.initial_data:
            raise serializers.ValidationError({
                "hospital_id": "Hospital is determined by your membership."
            })
        return attrs
