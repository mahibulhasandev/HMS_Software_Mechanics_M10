from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from apps.hospitals.models import Hospital
from apps.core.models import (
    Department,
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)

User = get_user_model()


# ==============================================================================
# AUTHENTICATION SERIALIZERS
# ==============================================================================

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=False,
        help_text="Email address or phone number.",
    )
    identifier = serializers.CharField(
        required=False,
        help_text="Email address or phone number.",
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        identifier = attrs.get("identifier") or attrs.get("username")
        password = attrs.get("password")

        if not identifier:
            raise serializers.ValidationError("An email or phone number is required.")

        request = self.context.get("request")
        user = authenticate(request=request, username=identifier, password=password)

        if not user:
            raise serializers.ValidationError(
                "Unable to log in with provided credentials. Please check your email/phone and password."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This user account is inactive. Please contact support or your hospital administrator."
            )

        attrs["user"] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "is_active", "date_joined"]


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is not correct.")
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        validate_password(value, user)
        return value

    def save(self, **kwargs):
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save()
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_new_password(self, value):
        user = self.context.get("user")
        validate_password(value, user)
        return value


# ==============================================================================
# DEPARTMENT & EMPLOYEE SERIALIZERS
# ==============================================================================

class DepartmentSerializer(serializers.ModelSerializer):
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)

    class Meta:
        model = Department
        fields = [
            "id",
            "hospital",
            "hospital_name",
            "name",
            "code",
            "department_type",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EmployeeSerializer(serializers.ModelSerializer):
    user_details = UserProfileSerializer(source="user", read_only=True)
    hospital_name = serializers.CharField(source="hospital.name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    approved_by_name = serializers.CharField(
        source="approved_by.user.full_name", read_only=True, default=None
    )

    class Meta:
        model = Employee
        fields = [
            "id",
            "user",
            "user_details",
            "hospital",
            "hospital_name",
            "department",
            "department_name",
            "employee_id",
            "designation",
            "role",
            "joining_date",
            "employment_status",
            "approval_status",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "approval_status",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]


class EmployeeRegistrationSerializer(serializers.ModelSerializer):
    """
    Handles employee application submission.
    Creates an employee record linked to an existing or newly authenticated user.
    Always initializes with approval_status = PENDING.
    """

    class Meta:
        model = Employee
        fields = [
            "id",
            "hospital",
            "department",
            "employee_id",
            "designation",
            "role",
            "joining_date",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        hospital = attrs.get("hospital")
        department = attrs.get("department")
        employee_id = attrs.get("employee_id")
        user = self.context["request"].user

        # 1. Department must belong to selected hospital
        if department and hospital and department.hospital_id != hospital.id:
            raise serializers.ValidationError({
                "department": "The selected department does not belong to this hospital."
            })

        # 2. User cannot have duplicate employment in same hospital
        if hospital and user and Employee.objects.filter(hospital=hospital, user=user).exists():
            raise serializers.ValidationError({
                "hospital": "You already have an employment record or pending registration at this hospital."
            })

        # 3. Employee ID uniqueness within hospital
        if hospital and employee_id and Employee.objects.filter(hospital=hospital, employee_id=employee_id).exists():
            raise serializers.ValidationError({
                "employee_id": "An employee with this Employee ID already exists in this hospital."
            })

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["user"] = user
        validated_data["approval_status"] = ApprovalStatus.PENDING
        validated_data["employment_status"] = EmploymentStatus.ACTIVE
        validated_data["approved_by"] = None
        validated_data["approved_at"] = None
        return super().create(validated_data)


class EmployeeStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ["employment_status", "designation", "department", "role"]

    def validate_department(self, department):
        employee = self.instance
        if department and department.hospital_id != employee.hospital_id:
            raise serializers.ValidationError("Department must belong to the same hospital.")
        return department
