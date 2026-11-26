from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import AccountingMembership


class AccountingRolePermission(BasePermission):
    message = "You do not have permission to access this accounting resource."

    READ_ROLES = {
        AccountingMembership.Role.ADMIN,
        AccountingMembership.Role.ACCOUNTANT,
        AccountingMembership.Role.STAFF,
    }

    WRITE_ROLES = {
        AccountingMembership.Role.ADMIN,
        AccountingMembership.Role.ACCOUNTANT,
    }

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        hospital_id = getattr(request, "accounting_hospital_id", None)
        role = getattr(request, "accounting_role", None)

        if not user or not user.is_authenticated or not user.is_active:
            return False

        if hospital_id is None or role not in self.READ_ROLES:
            return False

        if request.method in SAFE_METHODS:
            return True

        if request.method in ("POST", "PUT", "PATCH"):
            return role in self.WRITE_ROLES

        return False

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False

        object_hospital_id = getattr(obj, "hospital_id", None)

        if object_hospital_id is None:
            return False

        return str(object_hospital_id) == str(
            request.accounting_hospital_id
        )
