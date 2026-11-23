from rest_framework import serializers

from .models import (
    Appointment,
    Consultation,
    Diagnosis,
    DoctorSchedule,
    Prescription,
    PrescriptionItem,
)


class DoctorScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorSchedule
        fields = [
            "id",
            "hospital",
            "doctor_id",
            "weekday",
            "start_time",
            "end_time",
            "slot_minutes",
            "max_patients",
            "valid_from",
            "valid_to",
        ]
        read_only_fields = ["id"]

    def validate_weekday(self, value):
        if value < 0 or value > 6:
            raise serializers.ValidationError("Weekday must be between 0 and 6.")
        return value

    def validate_slot_minutes(self, value):
        if value <= 0:
            raise serializers.ValidationError("Slot minutes must be greater than 0.")
        return value

    def validate_max_patients(self, value):
        if value <= 0:
            raise serializers.ValidationError("Max patients must be greater than 0.")
        return value

    def validate(self, attrs):
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "End time must be after start time."}
            )

        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        if valid_from and valid_to and valid_to < valid_from:
            raise serializers.ValidationError(
                {"valid_to": "Valid to date cannot be earlier than valid from date."}
            )

        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            "id",
            "hospital",
            "patient_id",
            "doctor_id",
            "patient_visit_id",
            "appointment_date",
            "start_time",
            "status",
            "booking_source",
        ]
        read_only_fields = ["id"]


class ConsultationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultation
        fields = [
            "id",
            "hospital",
            "patient_visit_id",
            "doctor_id",
            "appointment_id",
            "complaints",
            "examination_notes",
            "advice",
            "follow_up_date",
        ]
        read_only_fields = ["id"]


class DiagnosisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diagnosis
        fields = [
            "id",
            "hospital",
            "consultation",
            "diagnosis_name",
            "icd_code",
            "diagnosis_type",
        ]
        read_only_fields = ["id"]


class PrescriptionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "hospital",
            "prescription",
            "medicine_id",
            "dosage",
            "frequency",
            "duration_days",
            "quantity",
            "instructions",
        ]
        read_only_fields = ["id"]

    def validate_duration_days(self, value):
        if value <= 0:
            raise serializers.ValidationError("Duration days must be greater than 0.")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0.")
        return value


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True, read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "hospital",
            "consultation",
            "prescribed_at",
            "notes",
            "items",
        ]
        read_only_fields = ["id"]