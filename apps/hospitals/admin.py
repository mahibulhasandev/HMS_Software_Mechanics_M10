
from django.contrib import admin

from .models import Hospital


@admin.register(Hospital)
class HospitalAdmin(admin.ModelAdmin):
    list_display = (
        "registration_number",
        "name",
        "phone",
        "email",
        "status",
    )

    list_filter = ("status",)
    search_fields = (
        "registration_number",
        "name",
        "email",
        "phone",
    )
