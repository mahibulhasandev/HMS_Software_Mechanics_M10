from django.contrib import admin
from apps.core.admin import BaseHospitalScopedAdmin
from .models import Patient, PatientVisit


@admin.register(Patient)
class PatientAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "patient_number",
        "first_name",
        "last_name",
        "phone",
        "gender",
        "status",
        "hospital",
    )

    list_filter = ("gender", "status", "hospital")
    search_fields = (
        "patient_number",
        "first_name",
        "last_name",
        "phone",
    )

    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PatientVisit)
class PatientVisitAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "visit_number",
        "patient",
        "hospital",
        "visit_type",
        "visit_date",
        "status",
    )

    list_filter = ("visit_type", "status", "hospital")
    search_fields = (
        "visit_number",
        "patient__patient_number",
        "patient__first_name",
        "patient__phone",
    )

    readonly_fields = ("id", "created_at", "updated_at")
