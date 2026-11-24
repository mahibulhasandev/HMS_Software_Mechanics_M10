from rest_framework import permissions
from django.apps import apps


def get_employee_model_and_enums():
    """
    Dynamically loads the Employee model and enums from apps.core if registered in INSTALLED_APPS.
    Returns (Employee, EmployeeRole, ApprovalStatus, EmploymentStatus) or (None, None, None, None).
    """
    if apps.is_installed("core") or apps.is_installed("apps.core"):
        try:
            Employee = apps.get_model("core", "Employee")
            from apps.core.models import EmployeeRole, ApprovalStatus, EmploymentStatus
            return Employee, EmployeeRole, ApprovalStatus, EmploymentStatus
        except (LookupError, ImportError):
            pass
    return None, None, None, None


def get_active_employee_for_hospital(user, hospital_id):
    """
    Resolves the authenticated user's Employee membership for the given hospital.
    Must be active and approved. Returns None if invalid, unauthorized, or core is not installed.
    """
    if not user or not user.is_authenticated or not hospital_id:
        return None

    Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
    if not Employee:
        return None

    return Employee.objects.filter(
        user=user,
        hospital_id=hospital_id,
        approval_status=ApprovalStatus.APPROVED,
        employment_status=EmploymentStatus.ACTIVE,
    ).first()


class IsHospitalStaffForPatient(permissions.BasePermission):
    """
    RBAC permission for Patient and PatientVisit endpoints:
    - Rejects unauthenticated requests.
    - Superusers are granted platform administrative access.
    - If core is installed:
        * Resolves the hospital context from header 'X-Hospital-ID', query parameter 'hospital',
          or request data 'hospital'.
        * Validates that the user has an ACTIVE and APPROVED Employee record in that hospital.
        * Enforces role-based permissions:
            - SAFE_METHODS (GET, HEAD, OPTIONS): Hospital Admin, Doctor, Nurse, Receptionist.
            - POST (create): Hospital Admin, Doctor, Nurse, Receptionist.
            - PUT / PATCH: Hospital Admin, Doctor, Nurse, Receptionist (for Patient) or Admin/Doctor/Nurse (for Visit).
            - DELETE: Strictly Hospital Admin.
            - Other roles (e.g. Accountant, Lab Tech, General Staff): Denied.
    - If core is not installed (e.g. legacy/default settings):
        * Falls back safely to requiring an authenticated staff user or superuser.
    """

    message = "You do not have authorized, active staff access for this hospital."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if not Employee:
            # Fallback if core app is not in INSTALLED_APPS
            return request.user.is_staff

        patient_read_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }
        patient_create_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }
        patient_visit_update_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
        }
        patient_delete_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
        }

        # Extract hospital ID from header, query param, or request data
        hospital_id = (
            request.headers.get("X-Hospital-ID")
            or request.query_params.get("hospital")
            or (request.data.get("hospital") if isinstance(request.data, dict) else None)
        )

        if not hospital_id:
            # If no hospital context provided, check if user has at least one active approved employment
            allowed_roles = patient_read_roles if request.method in permissions.SAFE_METHODS else patient_create_roles
            return Employee.objects.filter(
                user=request.user,
                role__in=allowed_roles,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()

        # Validate employee membership in the specific hospital
        employee = get_active_employee_for_hospital(request.user, hospital_id)
        if not employee:
            return False

        # Attach active employee to request for view usage
        request.active_employee = employee

        is_visit = "visit" in getattr(view, "basename", "") or "PatientVisit" in view.__class__.__name__

        if request.method in permissions.SAFE_METHODS:
            return employee.role in patient_read_roles
        elif request.method == "POST":
            return employee.role in patient_create_roles
        elif request.method in ("PUT", "PATCH"):
            if is_visit:
                return employee.role in patient_visit_update_roles
            return employee.role in patient_create_roles
        elif request.method == "DELETE":
            return employee.role in patient_delete_roles

        return False

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = getattr(obj, "hospital_id", None)
        if not hospital_id:
            return False

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if not Employee:
            return request.user.is_staff

        employee = get_active_employee_for_hospital(request.user, hospital_id)
        if not employee:
            return False

        patient_read_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }
        patient_update_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }
        patient_visit_update_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
        }
        patient_delete_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
        }

        is_visit = "visit" in getattr(view, "basename", "") or "PatientVisit" in view.__class__.__name__

        if request.method in permissions.SAFE_METHODS:
            return employee.role in patient_read_roles
        elif request.method in ("PUT", "PATCH"):
            if is_visit:
                return employee.role in patient_visit_update_roles
            return employee.role in patient_update_roles
        elif request.method == "DELETE":
            return employee.role in patient_delete_roles

        return False
