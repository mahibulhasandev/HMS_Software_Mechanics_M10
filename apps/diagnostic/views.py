from django.shortcuts import render
from django.db.models import ProtectedError
from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from .models import (
    DiagnosticReport,
    DiagnosticTest,
    TestCategory,
    TestOrder,
    TestOrderItem,
    TestResult,
)
from .permissions import (
    IsHospitalStaffForDiagnostic,
    get_active_employee_for_hospital,
    get_employee_model_and_enums,
)
from .serializers import (
    DiagnosticReportSerializer,
    DiagnosticTestSerializer,
    TestCategorySerializer,
    TestOrderItemSerializer,
    TestOrderSerializer,
    TestResultSerializer,
)


class BaseDiagnosticViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet enforcing hospital-scoped queryset filtering and RBAC validation
    for all Diagnostic endpoints, aligned with PatientViewSet architecture.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsHospitalStaffForDiagnostic]

    def _get_requested_hospital_id(self):
        return (
            self.request.headers.get("X-Hospital-ID")
            or self.request.query_params.get("hospital_id")
            or self.request.query_params.get("hospital")
        )

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        requested_hospital_id = self._get_requested_hospital_id()

        if user.is_superuser:
            if requested_hospital_id:
                return qs.filter(hospital_id=requested_hospital_id)
            return qs

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = (
            get_employee_model_and_enums()
        )
        if not Employee:
            return qs

        diagnostic_read_roles = {
            EmployeeRole.HOSPITAL_ADMIN,
            EmployeeRole.LAB_TECHNICIAN,
            EmployeeRole.DOCTOR,
            EmployeeRole.NURSE,
            EmployeeRole.RECEPTIONIST,
        }

        if requested_hospital_id:
            emp = get_active_employee_for_hospital(user, requested_hospital_id)
            if not emp or emp.role not in diagnostic_read_roles:
                return qs.none()
            return qs.filter(hospital_id=requested_hospital_id)

        user_hospitals = Employee.objects.filter(
            user=user,
            role__in=diagnostic_read_roles,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).values_list("hospital_id", flat=True)

        return qs.filter(hospital_id__in=user_hospitals)

    def _verify_staff_for_hospital(self, hospital_id):
        user = self.request.user
        if user.is_superuser:
            return
        Employee, _, _, _ = get_employee_model_and_enums()
        if Employee:
            emp = get_active_employee_for_hospital(user, hospital_id)
            if not emp:
                raise PermissionDenied(
                    "You are not an authorized staff member for this hospital."
                )

    def perform_create(self, serializer):
        hospital_id = serializer.validated_data.get("hospital_id")
        if not hospital_id:
            raise ValidationError({"hospital_id": "Hospital ID is required."})
        self._verify_staff_for_hospital(hospital_id)
        serializer.save()

    def perform_update(self, serializer):
        instance = serializer.instance
        target_hospital_id = serializer.validated_data.get(
            "hospital_id", instance.hospital_id
        )
        if target_hospital_id != instance.hospital_id:
            raise ValidationError(
                {"hospital_id": "Changing hospital_id on an existing record is not allowed."}
            )
        self._verify_staff_for_hospital(instance.hospital_id)
        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not user.is_superuser:
            Employee, EmployeeRole, _, _ = get_employee_model_and_enums()
            if Employee:
                emp = get_active_employee_for_hospital(user, instance.hospital_id)
                if not emp or emp.role != EmployeeRole.HOSPITAL_ADMIN:
                    raise PermissionDenied(
                        "Only a Hospital Administrator can delete diagnostic records."
                    )
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                {"detail": "Cannot delete this record because related records exist."}
            )


class TestCategoryViewSet(BaseDiagnosticViewSet):
    queryset = TestCategory.objects.all()
    serializer_class = TestCategorySerializer
    filterset_fields = ["hospital_id", "is_active"]
    search_fields = ["name"]


class DiagnosticTestViewSet(BaseDiagnosticViewSet):
    queryset = DiagnosticTest.objects.select_related("category").all()
    serializer_class = DiagnosticTestSerializer
    filterset_fields = ["hospital_id", "category", "sample_type", "is_active"]
    search_fields = ["test_code", "name", "sample_type"]


class TestOrderViewSet(BaseDiagnosticViewSet):
    queryset = TestOrder.objects.prefetch_related("items", "items__diagnostic_test").all()
    serializer_class = TestOrderSerializer
    filterset_fields = ["hospital_id", "status"]
    search_fields = ["id", "status"]


class TestOrderItemViewSet(BaseDiagnosticViewSet):
    queryset = TestOrderItem.objects.select_related(
        "test_order", "diagnostic_test"
    ).all()
    serializer_class = TestOrderItemSerializer
    filterset_fields = ["hospital_id", "test_order", "diagnostic_test", "status"]
    search_fields = ["status", "diagnostic_test__name", "diagnostic_test__test_code"]


class TestResultViewSet(BaseDiagnosticViewSet):
    queryset = TestResult.objects.select_related(
        "test_order_item", "test_order_item__diagnostic_test"
    ).all()
    serializer_class = TestResultSerializer
    filterset_fields = ["hospital_id", "test_order_item", "flag"]
    search_fields = ["parameter_name", "result_value"]


class DiagnosticReportViewSet(BaseDiagnosticViewSet):
    queryset = DiagnosticReport.objects.select_related("test_order").all()
    serializer_class = DiagnosticReportSerializer
    filterset_fields = ["hospital_id", "test_order", "status"]
    search_fields = ["report_number", "status"]


