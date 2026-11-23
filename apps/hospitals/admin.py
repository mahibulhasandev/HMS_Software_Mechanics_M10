from django.contrib import admin
from .models import Hospital


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
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