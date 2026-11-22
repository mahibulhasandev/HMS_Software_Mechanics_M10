from django.contrib import admin

from .models import Doctor


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital",
        "employee_id",
        "employee_type",
        "license_number",
        "specialization",
        "consultation_fee",
    )
    list_filter = ("hospital", "specialization", "employee_type")
    search_fields = ("license_number", "specialization", "employee_id")