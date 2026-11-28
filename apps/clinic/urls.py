from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.clinic.views import (
    DoctorScheduleViewSet,
    AppointmentViewSet,
    DoctorAvailabilityView,
    ConsultationViewSet,
    DiagnosisViewSet,
)

router = DefaultRouter()
router.register(r"clinic/schedules", DoctorScheduleViewSet, basename="clinic-schedule")
router.register(r"clinic/appointments", AppointmentViewSet, basename="clinic-appointment")
router.register(r"clinic/consultations", ConsultationViewSet, basename="clinic-consultation")
router.register(r"clinic/diagnoses", DiagnosisViewSet, basename="clinic-diagnosis")

urlpatterns = [
    path(
        "clinic/doctors/<uuid:doctor_id>/available-slots/",
        DoctorAvailabilityView.as_view({"get": "list_slots"}),
        name="clinic-doctor-available-slots",
    ),
    path("", include(router.urls)),
]
