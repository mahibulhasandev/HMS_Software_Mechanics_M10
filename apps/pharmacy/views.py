
from django.db.models import ProtectedError

from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.patients.permissions import (
    get_employee_model_and_enums,
)

from .models import MedicineCategory
from .serializers import MedicineCategorySerializer
from .permissions import IsPharmacyStaff


class MedicineCategoryViewSet(viewsets.ModelViewSet):

    serializer_class = MedicineCategorySerializer

    authentication_classes = [SessionAuthentication]

    permission_classes = [
        IsAuthenticated,
        IsPharmacyStaff,
    ]

    def get_queryset(self):
        user = self.request.user

        queryset = MedicineCategory.objects.all()

        hospital_id = (
            self.request.headers.get("X-Hospital-ID")
            or self.request.query_params.get("hospital")
        )

        if user.is_superuser:
            if hospital_id:
                return queryset.filter(hospital_id=hospital_id)

            return queryset

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = (
            get_employee_model_and_enums()
        )

        if not Employee:
            return queryset.none()

        allowed_roles = [
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.PHARMACIST,
        ]

        employees = Employee.objects.filter(
            user=user,
            role__in=allowed_roles,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        if hospital_id:
            employees = employees.filter(
                hospital_id=hospital_id
            )

        hospital_ids = employees.values_list(
            "hospital_id",
            flat=True,
        )

        return queryset.filter(hospital_id__in=hospital_ids)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                "detail": (
                    "This category cannot be deleted because "
                    "medicines are linked to it."
                )
            })
