
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from django.db.models import ProtectedError
from rest_framework.exceptions import ValidationError

from .models import Patient, PatientVisit
from .serializers import (
    PatientSerializer,
    PatientVisitSerializer,
)


class PatientViewSet(viewsets.ModelViewSet):
    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({
                "detail": "Cannot delete this patient because visit records exist."
            })
    
    queryset = Patient.objects.select_related("hospital").all()
    serializer_class = PatientSerializer
    permission_classes = [AllowAny]

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


class PatientVisitViewSet(viewsets.ModelViewSet):
    queryset = PatientVisit.objects.select_related(
        "hospital",
        "patient",
    ).all()

    serializer_class = PatientVisitSerializer
    permission_classes = [AllowAny]

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
