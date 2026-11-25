import uuid
from rest_framework import permissions

from apps.patients.permissions import (
    get_active_employee_for_hospital,
    get_employee_model_and_enums,
)


def get_hospital_id_from_request(request, view=None):
    """
    Extracts and validates a hospital UUID from the request header, query parameters,
    or request body (dictionary payload). Returns a valid UUID string or None.
    """
    query_params = getattr(request, "query_params", getattr(request, "GET", {}))
    raw_data = getattr(request, "data", None)
    headers = getattr(request, "headers", {})

    raw_hospital_id = (
        headers.get("X-Hospital-ID")
        or query_params.get("hospital")
        or (raw_data.get("hospital") if isinstance(raw_data, dict) else None)
        or getattr(view, "hospital_id", None)
    )
    if not raw_hospital_id:
        return None

    try:
        return str(uuid.UUID(str(raw_hospital_id)))
    except (ValueError, TypeError, AttributeError):
        return None


class BaseHospitalScopedPermission(permissions.BasePermission):
    """
    Base permission for Clinic Department operations:
    - Rejects unauthenticated requests.
    - Superusers are granted platform administrative access.
    - Resolves the hospital context from header 'X-Hospital-ID', query parameter 'hospital',
      or request data 'hospital'.
    - Validates that the user has an ACTIVE and APPROVED Employee record in that hospital.
    - Sets request.active_employee according to the project convention.
    - Rejects missing or unauthorized hospital context.
    - Never trusts X-Hospital-ID without validating membership.
    """

    allowed_roles = set()
    message = "You do not have active, approved employee access for this hospital."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = get_hospital_id_from_request(request, view)
        if not hospital_id:
            self.message = "Hospital context (X-Hospital-ID header or hospital parameter) is required."
            return False

        employee = get_active_employee_for_hospital(request.user, hospital_id)
        if not employee:
            self.message = "You do not have active, approved employee access for this hospital."
            return False

        request.active_employee = employee

        if self.allowed_roles and employee.role not in self.allowed_roles:
            self.message = f"Role '{employee.role}' does not have permission to perform this action."
            return False

        return True

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = getattr(obj, "hospital_id", None)
        if not hospital_id:
            return False

        employee = get_active_employee_for_hospital(request.user, str(hospital_id))
        if not employee:
            return False

        request.active_employee = employee

        if self.allowed_roles and employee.role not in self.allowed_roles:
            return False

        return True


class IsHospitalAdmin(BaseHospitalScopedPermission):
    """
    Strictly grants access to active, approved Hospital Administrators within the tenant.
    """

    def __init__(self):
        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if EmployeeRole:
            self.allowed_roles = {EmployeeRole.HOSPITAL_ADMIN}
        else:
            self.allowed_roles = {"hospital_admin"}


class IsDoctor(BaseHospitalScopedPermission):
    """
    Grants access to active, approved Doctors within the target hospital tenant.
    """

    def __init__(self):
        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if EmployeeRole:
            self.allowed_roles = {EmployeeRole.DOCTOR, EmployeeRole.HOSPITAL_ADMIN}
        else:
            self.allowed_roles = {"doctor", "hospital_admin"}


class IsNurse(BaseHospitalScopedPermission):
    """
    Grants access to active, approved Nurses within the target hospital tenant.
    """

    def __init__(self):
        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if EmployeeRole:
            self.allowed_roles = {EmployeeRole.NURSE, EmployeeRole.HOSPITAL_ADMIN}
        else:
            self.allowed_roles = {"nurse", "hospital_admin"}


class IsReceptionist(BaseHospitalScopedPermission):
    """
    Grants access to active, approved Receptionists within the target hospital tenant.
    """

    def __init__(self):
        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if EmployeeRole:
            self.allowed_roles = {EmployeeRole.RECEPTIONIST, EmployeeRole.HOSPITAL_ADMIN}
        else:
            self.allowed_roles = {"receptionist", "hospital_admin"}


class IsClinicStaff(BaseHospitalScopedPermission):
    """
    Grants access to all clinical/reception staff involved in OPD workflows:
    - Hospital Admin
    - Doctor
    - Nurse
    - Receptionist
    """

    def __init__(self):
        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if EmployeeRole:
            self.allowed_roles = {
                EmployeeRole.HOSPITAL_ADMIN,
                EmployeeRole.DOCTOR,
                EmployeeRole.NURSE,
                EmployeeRole.RECEPTIONIST,
            }
        else:
            self.allowed_roles = {
                "hospital_admin",
                "doctor",
                "nurse",
                "receptionist",
            }
