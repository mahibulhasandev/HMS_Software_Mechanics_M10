
from rest_framework import permissions

from apps.patients.permissions import (
    get_employee_model_and_enums,
    get_active_employee_for_hospital,
)


class IsPharmacyStaff(permissions.BasePermission):
    message = "You do not have authorized Pharmacy access for this hospital."

    def get_hospital_id(self, request):
        return (
            request.headers.get("X-Hospital-ID")
            or request.query_params.get("hospital")
            or (
                request.data.get("hospital")
                if request.method not in permissions.SAFE_METHODS
                and isinstance(request.data, dict)
                else None
            )
        )

    def allowed_roles(self):
        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = (
            get_employee_model_and_enums()
        )

        if not Employee:
            return None, None

        return Employee, {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.PHARMACIST,
        }

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        Employee, allowed_roles = self.allowed_roles()

        if not Employee:
            return False

        hospital_id = self.get_hospital_id(request)

        if hospital_id:
            employee = get_active_employee_for_hospital(
                user, hospital_id
            )

            if not employee or employee.role not in allowed_roles:
                return False

            request.active_employee = employee

            if request.method == "DELETE":
                return employee.role == "hospital_admin"

            return True

        # POST must specify a hospital.
        if request.method == "POST":
            return False

        # For update/delete, object-level permission checks
        # the employee's access to the object's hospital.
        if request.method == "DELETE":
            allowed_roles = {"hospital_admin"}

        return Employee.objects.filter(
            user=user,
            role__in=allowed_roles,
            approval_status="approved",
            employment_status="active",
        ).exists()

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.is_superuser:
            return True

        employee = get_active_employee_for_hospital(
            user, obj.hospital_id
        )

        if not employee:
            return False

        if request.method == "DELETE":
            return employee.role == "hospital_admin"

        return employee.role in {
            "hospital_admin",
            "pharmacist",
        }
