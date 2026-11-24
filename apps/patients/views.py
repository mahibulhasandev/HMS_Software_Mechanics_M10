from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError, PermissionDenied
from django.db.models import ProtectedError
from django.apps import apps

from .models import Patient, PatientVisit
from .serializers import PatientSerializer, PatientVisitSerializer
from .permissions import IsHospitalStaffForPatient, get_active_employee_for_hospital, get_employee_model_and_enums


class PatientViewSet(viewsets.ModelViewSet):
    """
    Hospital-scoped, RBAC-protected API for Patient management.
    - List/Retrieve: Hospital Admin, Doctor, Nurse, Receptionist.
    - Create/Update: Hospital Admin, Doctor, Nurse, Receptionist.
    - Delete: Strictly Hospital Admin.
    """
    serializer_class = PatientSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsHospitalStaffForPatient]

    filterset_fields = [
        "hospital",
        "gender",
        "status",
        "blood_group",
    ]

    search_fields = [
        "patient_number",
        "first_name",
        "last_name",
        "phone",
        "email",
    ]

    def get_queryset(self):
        user = self.request.user
        qs = Patient.objects.select_related("hospital").all()

        if user.is_superuser:
            hospital_id = (
                self.request.headers.get("X-Hospital-ID")
                or self.request.query_params.get("hospital")
            )
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if not Employee:
            # Fallback for environment without core installed
            return qs

        patient_read_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }

        hospital_id = (
            self.request.headers.get("X-Hospital-ID")
            or self.request.query_params.get("hospital")
        )

        if hospital_id:
            emp = get_active_employee_for_hospital(user, hospital_id)
            if not emp or emp.role not in patient_read_roles:
                return qs.none()
            return qs.filter(hospital_id=hospital_id)

        user_hospitals = Employee.objects.filter(
            user=user,
            role__in=patient_read_roles,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).values_list("hospital_id", flat=True)

        return qs.filter(hospital_id__in=user_hospitals)

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")

        if not target_hospital:
            raise ValidationError({"hospital": "Hospital is required."})

        if not user.is_superuser:
            Employee, _, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, target_hospital.id)
                if not emp:
                    raise PermissionDenied("You are not an authorized staff member for this hospital.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance

        if not user.is_superuser:
            Employee, _, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, instance.hospital_id)
                if not emp:
                    raise PermissionDenied("You are not authorized to modify patient records for this hospital.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not user.is_superuser:
            Employee, EmployeeRole, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, instance.hospital_id)
                if not emp or emp.role != EmployeeRole.HOSPITAL_ADMIN:
                    raise PermissionDenied("Only a Hospital Administrator can delete patient records.")

        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                "detail": "Cannot delete this patient because visit records exist."
            })


class PatientVisitViewSet(viewsets.ModelViewSet):
    """
    Hospital-scoped, RBAC-protected API for PatientVisit management.
    - List/Retrieve: Hospital Admin, Doctor, Nurse, Receptionist.
    - Create: Hospital Admin, Doctor, Nurse, Receptionist.
    - Update: Hospital Admin, Doctor, Nurse.
    - Delete: Strictly Hospital Admin.
    """
    serializer_class = PatientVisitSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsHospitalStaffForPatient]

    filterset_fields = [
        "hospital",
        "patient",
        "visit_type",
        "status",
    ]

    search_fields = [
        "visit_number",
        "patient__patient_number",
        "patient__first_name",
        "patient__phone",
    ]

    ordering_fields = [
        "visit_date",
        "created_at",
    ]

    def get_queryset(self):
        user = self.request.user
        qs = PatientVisit.objects.select_related("hospital", "patient").all()

        if user.is_superuser:
            hospital_id = (
                self.request.headers.get("X-Hospital-ID")
                or self.request.query_params.get("hospital")
            )
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if not Employee:
            return qs

        patient_read_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }

        hospital_id = (
            self.request.headers.get("X-Hospital-ID")
            or self.request.query_params.get("hospital")
        )

        if hospital_id:
            emp = get_active_employee_for_hospital(user, hospital_id)
            if not emp or emp.role not in patient_read_roles:
                return qs.none()
            return qs.filter(hospital_id=hospital_id)

        user_hospitals = Employee.objects.filter(
            user=user,
            role__in=patient_read_roles,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).values_list("hospital_id", flat=True)

        return qs.filter(hospital_id__in=user_hospitals)

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")

        if not target_hospital:
            raise ValidationError({"hospital": "Hospital is required."})

        if not user.is_superuser:
            Employee, _, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, target_hospital.id)
                if not emp:
                    raise PermissionDenied("You are not an authorized staff member for this hospital.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance

        if not user.is_superuser:
            Employee, _, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, instance.hospital_id)
                if not emp:
                    raise PermissionDenied("You are not authorized to modify patient visit records for this hospital.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not user.is_superuser:
            Employee, EmployeeRole, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, instance.hospital_id)
                if not emp or emp.role != EmployeeRole.HOSPITAL_ADMIN:
                    raise PermissionDenied("Only a Hospital Administrator can delete patient visit records.")

        instance.delete()
