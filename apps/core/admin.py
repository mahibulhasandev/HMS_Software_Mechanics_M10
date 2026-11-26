from django.contrib import admin
from apps.patients.permissions import get_employee_model_and_enums


def get_user_approved_hospital_ids(user):
    """
    Returns a queryset/list of hospital IDs where the user has an
    APPROVED and ACTIVE Employee membership.
    If the user has no approved active employee record, returns an empty list.
    """
    if not user or not user.is_authenticated:
        return []

    Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
    if not Employee:
        return []

    return Employee.objects.filter(
        user=user,
        approval_status=ApprovalStatus.APPROVED,
        employment_status=EmploymentStatus.ACTIVE,
    ).values_list("hospital_id", flat=True)


class BaseHospitalScopedAdmin(admin.ModelAdmin):
    """
    Reusable ModelAdmin base providing strict multi-tenant isolation in Django Admin
    including changelist views, detail/change views, and autocomplete endpoints:
    - Superusers retain unrestricted global administrative access.
    - Staff users with approved, active Employee membership are strictly scoped
      to their authorized hospital(s).
    - If a user has no approved active employee record, they receive an empty queryset (0 records).
    - Multi-hospital employees can access only the union of their explicitly approved active memberships.
    - Never trusts client-supplied hospital IDs, query parameters, or headers.
    """

    hospital_lookup = "hospital_id"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs

        user_hospitals = get_user_approved_hospital_ids(request.user)

        # For the Hospital model itself, the primary key 'id' is the hospital_id
        if qs.model._meta.model_name == "hospital":
            return qs.filter(id__in=user_hospitals)

        # For models having a direct hospital FK or custom lookup
        lookup = {f"{self.hospital_lookup}__in": user_hospitals}
        return qs.filter(**lookup)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Scope foreign key dropdown choices to the user's authorized hospital(s) if not a superuser.
        """
        if not request.user.is_superuser:
            user_hospitals = get_user_approved_hospital_ids(request.user)

            if db_field.name == "hospital":
                kwargs["queryset"] = db_field.related_model.objects.filter(id__in=user_hospitals)
            elif hasattr(db_field.related_model, "hospital"):
                kwargs["queryset"] = db_field.related_model.objects.filter(hospital_id__in=user_hospitals)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True

        user_hospitals = get_user_approved_hospital_ids(request.user)
        obj_hospital_id = getattr(obj, "hospital_id", getattr(obj, "id", None) if obj._meta.model_name == "hospital" else None)
        return obj_hospital_id in user_hospitals

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True

        user_hospitals = get_user_approved_hospital_ids(request.user)
        obj_hospital_id = getattr(obj, "hospital_id", getattr(obj, "id", None) if obj._meta.model_name == "hospital" else None)
        return obj_hospital_id in user_hospitals

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True

        user_hospitals = get_user_approved_hospital_ids(request.user)
        obj_hospital_id = getattr(obj, "hospital_id", getattr(obj, "id", None) if obj._meta.model_name == "hospital" else None)
        return obj_hospital_id in user_hospitals
