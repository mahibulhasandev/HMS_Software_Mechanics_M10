from django.contrib import admin

from .models import (
    Appointment,
    Consultation,
    Diagnosis,
    DoctorSchedule,
    Prescription,
    PrescriptionItem,
)

admin.site.register(DoctorSchedule)
admin.site.register(Appointment)
admin.site.register(Consultation)
admin.site.register(Diagnosis)
admin.site.register(Prescription)
admin.site.register(PrescriptionItem)
