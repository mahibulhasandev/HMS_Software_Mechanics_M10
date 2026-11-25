import copy
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Doctor, DoctorDepartment, DoctorSpecialization


def run_model_clean(instance):
    try:
        instance.clean()
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise serializers.ValidationError(exc.message_dict)
        raise serializers.ValidationError(exc.messages)


class DoctorDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorDepartment
        fields = [
            "id",
            "hospital",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else DoctorDepartment()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs


class DoctorSpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DoctorSpecialization
        fields = [
            "id",
            "hospital",
            "department",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else DoctorSpecialization()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs


class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Doctor
        fields = [
            "id",
            "hospital",
            "department",
            "specialization",
            "doctor_code",
            "first_name",
            "last_name",
            "full_name",
            "gender",
            "date_of_birth",
            "phone",
            "email",
            "address",
            "profile_picture",
            "registration_number",
            "qualifications",
            "experience_years",
            "employment_type",
            "consultation_fee",
            "follow_up_fee",
            "status",
            "joined_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "full_name", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = copy.copy(self.instance) if self.instance is not None else Doctor()
        for attr, value in attrs.items():
            setattr(instance, attr, value)
        run_model_clean(instance)
        return attrs
