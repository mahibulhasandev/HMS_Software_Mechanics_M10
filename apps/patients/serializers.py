
from rest_framework import serializers
from django.utils import timezone

from .models import Patient, PatientVisit


class PatientSerializer(serializers.ModelSerializer):

    class Meta:
        model = Patient
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_date_of_birth(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value


class PatientVisitSerializer(serializers.ModelSerializer):

    patient_details = PatientSerializer(
        source="patient",
        read_only=True,
    )

    class Meta:
        model = PatientVisit
        fields = "__all__"
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "patient_details",
        ]

    def validate(self, attrs):
        hospital = attrs.get(
            "hospital",
            getattr(self.instance, "hospital", None),
        )
        patient = attrs.get(
            "patient",
            getattr(self.instance, "patient", None),
        )

        if hospital and patient and patient.hospital_id != hospital.id:
            raise serializers.ValidationError({
                "patient": "Patient does not belong to this hospital."
            })

        return attrs
