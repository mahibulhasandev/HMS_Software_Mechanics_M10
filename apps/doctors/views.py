from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import Doctor, DoctorDepartment, DoctorSpecialization
from .serializers import (
    DoctorDepartmentSerializer,
    DoctorSerializer,
    DoctorSpecializationSerializer,
)


class ProtectedDeleteMixin:
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {"detail": "Cannot delete this record because it is referenced by other records."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DoctorDepartmentViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = DoctorDepartment.objects.select_related("hospital").all()
    serializer_class = DoctorDepartmentSerializer
    filterset_fields = ["hospital", "is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]


class DoctorSpecializationViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = DoctorSpecialization.objects.select_related("hospital", "department").all()
    serializer_class = DoctorSpecializationSerializer
    filterset_fields = ["hospital", "department", "is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]


class DoctorViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Doctor.objects.select_related("hospital", "department", "specialization").all()
    serializer_class = DoctorSerializer
    filterset_fields = [
        "hospital",
        "department",
        "specialization",
        "gender",
        "employment_type",
        "status",
    ]
    search_fields = [
        "doctor_code",
        "first_name",
        "last_name",
        "phone",
        "email",
        "registration_number",
    ]
    ordering_fields = ["first_name", "doctor_code", "consultation_fee", "created_at"]
