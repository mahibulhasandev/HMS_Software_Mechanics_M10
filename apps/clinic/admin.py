
from django.contrib import admin

from .models import (
    DoctorSchedule,
    Appointment,
    Consultation,
    Diagnosis,
    Prescription,
    PrescriptionItem,
)


# ==========================================================
# DOCTOR SCHEDULE ADMIN
# TODO: [DOCTOR APP INTEGRATION]
# Add doctor / doctor_id to list_display after integration.
# ==========================================================

@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "hospital",
        "weekday",
        "start_time",
        "end_time",
        "slot_minutes",
        "max_patients",
        "is_available",
    )

    list_filter = (
        "hospital",
        "weekday",
        "is_available",
    )

    search_fields = (
        "id",
    )

    ordering = (
        "weekday",
        "start_time",
    )


# ==========================================================
# APPOINTMENT ADMIN
# TODO: [DOCTOR APP INTEGRATION]
# Add doctor / doctor_id after Doctor model integration.
# ==========================================================

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "hospital",
        "patient",
        "patient_visit",
        "appointment_date",
        "start_time",
        "status",
        "booking_source",
    )

    list_filter = (
        "hospital",
        "status",
        "booking_source",
        "appointment_date",
    )

    search_fields = (
        "id",
        "patient__id",
        "patient_visit__id",
    )

    ordering = (
        "-appointment_date",
        "-start_time",
    )


# ==========================================================
# CONSULTATION ADMIN
# TODO: [DOCTOR APP INTEGRATION]
# Add doctor / doctor_id after Doctor model integration.
# ==========================================================

@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "hospital",
        "patient_visit",
        "appointment",
        "follow_up_date",
        "created_at",
    )

    list_filter = (
        "hospital",
        "follow_up_date",
    )

    search_fields = (
        "id",
        "patient_visit__id",
    )

    ordering = (
        "-created_at",
    )


# ==========================================================
# DIAGNOSIS ADMIN
# ==========================================================

@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "hospital",
        "consultation",
        "diagnosis_name",
        "icd_code",
        "diagnosis_type",
        "created_at",
    )

    list_filter = (
        "hospital",
        "diagnosis_type",
    )

    search_fields = (
        "diagnosis_name",
        "icd_code",
        "consultation__id",
    )

    ordering = (
        "-created_at",
    )


# ==========================================================
# PRESCRIPTION ADMIN
# ==========================================================

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "hospital",
        "consultation",
        "prescribed_at",
    )

    list_filter = (
        "hospital",
        "prescribed_at",
    )

    search_fields = (
        "id",
        "consultation__id",
    )

    ordering = (
        "-prescribed_at",
    )


# ==========================================================
# PRESCRIPTION ITEM ADMIN
# TODO: [PHARMACY APP INTEGRATION]
# Add medicine / medicine_id after Medicine model integration.
# ==========================================================

@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "hospital",
        "prescription",
        "dosage",
        "frequency",
        "duration_days",
        "quantity",
    )

    list_filter = (
        "hospital",
    )

    search_fields = (
        "id",
        "prescription__id",
    )
