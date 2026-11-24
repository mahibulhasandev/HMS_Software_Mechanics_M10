from rest_framework import permissions
from apps.core.models import Employee, EmployeeRole, ApprovalStatus, EmploymentStatus


def get_active_employee_for_hospital(user, hospital_id):
    """
    Resolves the authenticated user's Employee profile for the specified hospital.
    Must be active and approved.
    """
    if not user or not user.is_authenticated or not hospital_id:
        return None

    return Employee.objects.filter(
        user=user,
        hospital_id=hospital_id,
        approval_status=ApprovalStatus.APPROVED,
        employment_status=EmploymentStatus.ACTIVE,
    ).first()


class IsHospitalStaff(permissions.BasePermission):
    """
    Grants access only if the authenticated user holds an active, approved
    employment contract in the requested hospital context.
    """

    message = "You do not have active, approved staff access for this hospital."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Superusers bypass tenant employee checks for platform administration
        if request.user.is_superuser:
            return True

        hospital_id = (
            request.headers.get("X-Hospital-ID")
            or request.query_params.get("hospital")
            or getattr(view, "hospital_id", None)
        )

        if not hospital_id:
            # Check if user has at least one active employment anywhere
            return Employee.objects.filter(
                user=request.user,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()

        employee = get_active_employee_for_hospital(request.user, hospital_id)
        if employee:
            request.active_employee = employee
            return True
        return False


class IsHospitalAdmin(permissions.BasePermission):
    """
    Grants access only to verified Hospital Administrators within the target hospital.
    """

    message = "Only an authorized Hospital Administrator can perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = (
            request.headers.get("X-Hospital-ID")
            or request.query_params.get("hospital")
            or getattr(view, "hospital_id", None)
        )

        if not hospital_id:
            # If no hospital specified, check if user is admin in any hospital
            return Employee.objects.filter(
                user=request.user,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()

        admin_emp = Employee.objects.filter(
            user=request.user,
            hospital_id=hospital_id,
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).first()

        if admin_emp:
            request.active_employee = admin_emp
            return True
        return False

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = getattr(obj, "hospital_id", None)
        if not hospital_id:
            return False

        return Employee.objects.filter(
            user=request.user,
            hospital_id=hospital_id,
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).exists()


class IsHospitalAdminOrReadOnlyStaff(permissions.BasePermission):
    """
    Hospital-scoped permission:
    - SAFE_METHODS (GET, HEAD, OPTIONS): Requires IsHospitalStaff (approved staff in the hospital).
    - Unsafe methods (POST, PUT, PATCH, DELETE): Requires IsHospitalAdmin (hospital admin in the hospital).
    """

    message = "You do not have permission to perform this action. Administrator privileges required for modifications."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        if request.method in permissions.SAFE_METHODS:
            return IsHospitalStaff().has_permission(request, view)
        return IsHospitalAdmin().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = getattr(obj, "hospital_id", None)
        if not hospital_id:
            return False

        if request.method in permissions.SAFE_METHODS:
            return Employee.objects.filter(
                user=request.user,
                hospital_id=hospital_id,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()

        return Employee.objects.filter(
            user=request.user,
            hospital_id=hospital_id,
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).exists()




class HasRolePermission(permissions.BasePermission):
    """
    Factory-style permission checking against specific allowed employee roles.
    """

    allowed_roles = []

    def __init__(self, allowed_roles=None):
        if allowed_roles:
            self.allowed_roles = allowed_roles

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        hospital_id = (
            request.headers.get("X-Hospital-ID")
            or request.query_params.get("hospital")
            or getattr(view, "hospital_id", None)
        )

        roles = getattr(view, "allowed_roles", self.allowed_roles)

        emp = Employee.objects.filter(
            user=request.user,
            hospital_id=hospital_id,
            role__in=roles,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).first()

        return emp is not None
