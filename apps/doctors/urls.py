from rest_framework.routers import DefaultRouter

from .views import (
    DoctorDepartmentViewSet,
    DoctorSpecializationViewSet,
    DoctorViewSet,
)

router = DefaultRouter()
router.register(r"doctor-departments", DoctorDepartmentViewSet, basename="doctor-department")
router.register(r"doctor-specializations", DoctorSpecializationViewSet, basename="doctor-specialization")
router.register(r"doctors", DoctorViewSet, basename="doctor")

urlpatterns = router.urls
