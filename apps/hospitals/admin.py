from django.contrib import admin
from apps.core.admin import BaseHospitalScopedAdmin
from .models import Hospital


@admin.register(Hospital)
class HospitalAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "name",
        "registration_number",
        "phone",
        "email",
        "status",
    )
    list_filter = ("status",)
    search_fields = (
        "name",
        "registration_number",
        "phone",
    )
