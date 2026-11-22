
from django.contrib import admin

from .models import (
    DoctorSchedule,
    Appointment,
    Consultation,
    Diagnosis,
    Prescription,
    PrescriptionItem,
)


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "doctor_id",
        "weekday",
        "start_time",
        "end_time",
        "slot_minutes",
        "max_patients",
        "valid_from",
        "valid_to",
    )

    list_filter = (
        "weekday",
        "hospital",
    )

    search_fields = (
        "doctor_id",
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "patient_id",
        "doctor_id",
        "appointment_date",
        "start_time",
        "status",
        "booking_source",
    )

    list_filter = (
        "status",
        "booking_source",
        "appointment_date",
    )

    search_fields = (
        "patient_id",
        "doctor_id",
    )


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "patient_visit_id",
        "doctor_id",
        "appointment_id",
        "follow_up_date",
    )

    search_fields = (
        "patient_visit_id",
        "doctor_id",
    )


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "consultation",
        "diagnosis_name",
        "diagnosis_type",
    )

    search_fields = (
        "diagnosis_name",
        "icd_code",
    )


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "consultation",
        "prescribed_at",
    )


@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "prescription",
        "medicine_id",
        "dosage",
        "quantity",
    )

    search_fields = (
        "medicine_id",
        "dosage",
    )
