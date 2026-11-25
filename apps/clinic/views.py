from django.db.models import ProtectedError
from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import (
    Appointment,
    Consultation,
    Diagnosis,
    DoctorSchedule,
    Prescription,
    PrescriptionItem,
)
from .serializers import (
    AppointmentSerializer,
    ConsultationSerializer,
    DiagnosisSerializer,
    DoctorScheduleSerializer,
    PrescriptionItemSerializer,
    PrescriptionSerializer,
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


class DoctorScheduleViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = DoctorSchedule.objects.select_related("hospital", "doctor").all()
    serializer_class = DoctorScheduleSerializer
    filterset_fields = ["hospital", "doctor", "weekday", "is_available"]
    ordering_fields = ["weekday", "start_time", "created_at"]


class AppointmentViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Appointment.objects.select_related(
        "hospital", "patient", "doctor", "patient_visit"
    ).all()
    serializer_class = AppointmentSerializer
    filterset_fields = [
        "hospital",
        "patient",
        "doctor",
        "appointment_date",
        "status",
        "booking_source",
    ]
    search_fields = ["reason", "patient__first_name", "patient__patient_number"]
    ordering_fields = ["appointment_date", "appointment_time", "created_at"]


class ConsultationViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Consultation.objects.select_related(
        "hospital", "patient_visit", "doctor", "appointment"
    ).all()
    serializer_class = ConsultationSerializer
    filterset_fields = ["hospital", "patient_visit", "doctor", "follow_up_date"]
    search_fields = ["complaints", "examination_notes", "advice"]
    ordering_fields = ["created_at", "follow_up_date"]


class DiagnosisViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Diagnosis.objects.select_related("hospital", "consultation").all()
    serializer_class = DiagnosisSerializer
    filterset_fields = ["hospital", "consultation", "diagnosis_type"]
    search_fields = ["diagnosis_name", "icd_code"]
    ordering_fields = ["created_at", "diagnosis_name"]


class PrescriptionViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = Prescription.objects.select_related("hospital", "consultation").prefetch_related("items").all()
    serializer_class = PrescriptionSerializer
    filterset_fields = ["hospital", "consultation"]
    search_fields = ["notes"]
    ordering_fields = ["prescribed_at"]


class PrescriptionItemViewSet(ProtectedDeleteMixin, viewsets.ModelViewSet):
    queryset = PrescriptionItem.objects.select_related("hospital", "prescription").all()
    serializer_class = PrescriptionItemSerializer
    filterset_fields = ["hospital", "prescription", "medicine_id"]
    search_fields = ["dosage", "frequency", "instructions"]
    ordering_fields = ["id"]
