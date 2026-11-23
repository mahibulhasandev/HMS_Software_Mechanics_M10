
from rest_framework.routers import DefaultRouter

from .views import PatientViewSet, PatientVisitViewSet

router = DefaultRouter()

router.register(
    r"patients",
    PatientViewSet,
    basename="patient",
)

router.register(
    r"patient-visits",
    PatientVisitViewSet,
    basename="patient-visit",
)

urlpatterns = router.urls
