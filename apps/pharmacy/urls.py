
from rest_framework.routers import DefaultRouter

from .views import MedicineCategoryViewSet


router = DefaultRouter()

router.register(
    r"medicine-categories",
    MedicineCategoryViewSet,
    basename="medicine-category",
)

urlpatterns = router.urls
