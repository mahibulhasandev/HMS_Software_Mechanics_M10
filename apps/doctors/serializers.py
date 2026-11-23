from rest_framework import serializers

from .models import Doctor


class DoctorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = [
            "id",
            "hospital",
            "employee_id",
            "employee_type",
            "license_number",
            "specialization",
            "consultation_fee",
        ]
        read_only_fields = ["id"]

    def validate_consultation_fee(self, value):
        if value < 0:
            raise serializers.ValidationError("Consultation fee cannot be negative.")
        return value