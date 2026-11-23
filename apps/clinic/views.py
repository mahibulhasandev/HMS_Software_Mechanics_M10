from rest_framework import viewsets

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


class DoctorScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = DoctorScheduleSerializer
    queryset = DoctorSchedule.objects.select_related("hospital").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        doctor_id = self.request.query_params.get("doctor_id")
        weekday = self.request.query_params.get("weekday")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)
        if weekday is not None:
            queryset = queryset.filter(weekday=weekday)
        return queryset


class AppointmentViewSet(viewsets.ModelViewSet):
    serializer_class = AppointmentSerializer
    queryset = Appointment.objects.select_related("hospital").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        doctor_id = self.request.query_params.get("doctor_id")
        patient_id = self.request.query_params.get("patient_id")
        appointment_date = self.request.query_params.get("appointment_date")
        appointment_status = self.request.query_params.get("status")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        if appointment_date:
            queryset = queryset.filter(appointment_date=appointment_date)
        if appointment_status:
            queryset = queryset.filter(status=appointment_status)
        return queryset


class ConsultationViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationSerializer
    queryset = Consultation.objects.select_related("hospital").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        doctor_id = self.request.query_params.get("doctor_id")
        patient_visit_id = self.request.query_params.get("patient_visit_id")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if doctor_id:
            queryset = queryset.filter(doctor_id=doctor_id)
        if patient_visit_id:
            queryset = queryset.filter(patient_visit_id=patient_visit_id)
        return queryset


class DiagnosisViewSet(viewsets.ModelViewSet):
    serializer_class = DiagnosisSerializer
    queryset = Diagnosis.objects.select_related("hospital", "consultation").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        consultation_id = self.request.query_params.get("consultation")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if consultation_id:
            queryset = queryset.filter(consultation_id=consultation_id)
        return queryset


class PrescriptionViewSet(viewsets.ModelViewSet):
    serializer_class = PrescriptionSerializer
    queryset = (
        Prescription.objects.select_related("hospital", "consultation")
        .prefetch_related("items")
        .all()
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        consultation_id = self.request.query_params.get("consultation")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if consultation_id:
            queryset = queryset.filter(consultation_id=consultation_id)
        return queryset


class PrescriptionItemViewSet(viewsets.ModelViewSet):
    serializer_class = PrescriptionItemSerializer
    queryset = PrescriptionItem.objects.select_related("hospital", "prescription").all()

    def get_queryset(self):
        queryset = super().get_queryset()
        hospital_id = self.request.query_params.get("hospital")
        prescription_id = self.request.query_params.get("prescription")

        if hospital_id:
            queryset = queryset.filter(hospital_id=hospital_id)
        if prescription_id:
            queryset = queryset.filter(prescription_id=prescription_id)
        return queryset