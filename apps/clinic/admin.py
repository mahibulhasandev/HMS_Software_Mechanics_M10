
from django.contrib import admin

from .models import DoctorSchedule


@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "doctor",
        "hospital",
        "weekday",
        "start_time",
        "end_time",
        "slot_minutes",
        "max_patients",
        "valid_from",
        "valid_to",
    )

    list_filter = ("weekday", "hospital")
    search_fields = ("doctor__employee__full_name",)
    ordering = ("weekday", "start_time")
