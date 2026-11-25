from rest_framework.routers import DefaultRouter

from .views import (
    AppointmentViewSet,
    ConsultationViewSet,
    DiagnosisViewSet,
    DoctorScheduleViewSet,
    PrescriptionItemViewSet,
    PrescriptionViewSet,
)

router = DefaultRouter()
router.register(r"doctor-schedules", DoctorScheduleViewSet, basename="doctor-schedule")
router.register(r"appointments", AppointmentViewSet, basename="appointment")
router.register(r"consultations", ConsultationViewSet, basename="consultation")
router.register(r"diagnoses", DiagnosisViewSet, basename="diagnosis")
router.register(r"prescriptions", PrescriptionViewSet, basename="prescription")
router.register(r"prescription-items", PrescriptionItemViewSet, basename="prescription-item")

urlpatterns = router.urls
