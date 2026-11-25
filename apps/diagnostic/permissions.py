from django.apps import apps
from rest_framework import permissions


def get_employee_model_and_enums():
    """
    Dynamically loads Employee model and enums from apps.core if installed.
    Returns (Employee, EmployeeRole, ApprovalStatus, EmploymentStatus) or (None, None, None, None).
    """
    if apps.is_installed("core") or apps.is_installed("apps.core"):
        try:
            Employee = apps.get_model("core", "Employee")
            from apps.core.models import (
                ApprovalStatus,
                EmployeeRole,
                EmploymentStatus,
            )

            return Employee, EmployeeRole, ApprovalStatus, EmploymentStatus
        except (LookupError, ImportError):
            pass
    return None, None, None, None


def get_active_employee_for_hospital(user, hospital_id):
    """
    Returns an active and approved Employee record for the given user and hospital_id.
    """
    if not user or not user.is_authenticated or not hospital_id:
        return None

    Employee, _, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
    if not Employee:
        return None

    return (
        Employee.objects.filter(
            user=user,
            hospital_id=hospital_id,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )
        .first()
    )


def _extract_hospital_id(request, obj=None):
    if obj is not None and getattr(obj, "hospital_id", None):
        return obj.hospital_id

    if request.headers.get("X-Hospital-ID"):
        return request.headers.get("X-Hospital-ID")

    if request.query_params.get("hospital_id"):
        return request.query_params.get("hospital_id")

    if request.query_params.get("hospital"):
        return request.query_params.get("hospital")

    if isinstance(request.data, dict):
        return request.data.get("hospital_id") or request.data.get("hospital")

    return None


class IsHospitalStaffForDiagnostic(permissions.BasePermission):
    """
    RBAC and hospital-scoped permission for Diagnostic endpoints.
    """

    message = "You do not have authorized, active staff access for this hospital."

    def _allowed_roles_for_method(self, request, EmployeeRole):
        read_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.LAB_TECHNICIAN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }
        write_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.LAB_TECHNICIAN,
            EmployeeRole.DOCTOR,
        }
        delete_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
        }

        if request.method in permissions.SAFE_METHODS:
            return read_roles
        if request.method in ("POST", "PUT", "PATCH"):
            return write_roles
        if request.method == "DELETE":
            return delete_roles
        return set()

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = (
            get_employee_model_and_enums()
        )
        if not Employee:
            return request.user.is_staff

        allowed_roles = self._allowed_roles_for_method(request, EmployeeRole)
        hospital_id = _extract_hospital_id(request)

        if not hospital_id:
            return Employee.objects.filter(
                user=request.user,
                role__in=allowed_roles,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()

        employee = get_active_employee_for_hospital(request.user, hospital_id)
        if not employee:
            return False

        request.active_employee = employee
        return employee.role in allowed_roles

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        Employee, EmployeeRole, _, _ = get_employee_model_and_enums()
        if not Employee:
            return request.user.is_staff

        hospital_id = _extract_hospital_id(request, obj=obj)
        if not hospital_id:
            return False

        employee = get_active_employee_for_hospital(request.user, hospital_id)
        if not employee:
            return False

        request.active_employee = employee
        allowed_roles = self._allowed_roles_for_method(request, EmployeeRole)
        return employee.role in allowed_roles