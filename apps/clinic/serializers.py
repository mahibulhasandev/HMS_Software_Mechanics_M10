import copy
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import (
    Appointment,
    Consultation,
    Diagnosis,
    DoctorSchedule,
    Prescription,
    PrescriptionItem,
)


def run_model_clean(instance):
    try:
        instance.clean()
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise serializers.ValidationError(exc.message_dict)
        raise serializers.ValidationError(exc.messages)


class DoctorScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorSchedule
        fields = [
            "id",
            "hospital",
            "doctor",
            "weekday",
            "start_time",
            "end_time",
            "slot_minutes",
            "max_patients",
            "valid_from",
            "valid_to",
            "is_available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else DoctorSchedule()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        if instance.start_time and instance.end_time and instance.end_time <= instance.start_time:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})
        if instance.slot_minutes not in (15, 30, 45):
            raise serializers.ValidationError({"slot_minutes": "Slot minutes must be 15, 30, or 45."})
        if instance.max_patients < 1:
            raise serializers.ValidationError({"max_patients": "Max patients must be at least 1."})
        run_model_clean(instance)
        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = [
            "id",
            "hospital",
            "patient",
            "doctor",
            "patient_visit",
            "appointment_date",
            "appointment_time",
            "status",
            "booking_source",
            "reason",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else Appointment()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs


class ConsultationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consultation
        fields = [
            "id",
            "hospital",
            "patient_visit",
            "doctor",
            "appointment",
            "complaints",
            "examination_notes",
            "advice",
            "follow_up_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else Consultation()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs


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
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else Diagnosis()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs


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

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else PrescriptionItem()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        if instance.duration_days is not None and instance.duration_days < 1:
            raise serializers.ValidationError({"duration_days": "Duration days must be at least 1."})
        if instance.quantity is not None and instance.quantity < 1:
            raise serializers.ValidationError({"quantity": "Quantity must be at least 1."})
        run_model_clean(instance)
        return attrs


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
        read_only_fields = ["id", "prescribed_at", "items"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else Prescription()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs
