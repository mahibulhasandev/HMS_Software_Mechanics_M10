from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DiagnosticReportViewSet,
    DiagnosticTestViewSet,
    TestCategoryViewSet,
    TestOrderItemViewSet,
    TestOrderViewSet,
)

router = DefaultRouter()
router.register(r"categories", TestCategoryViewSet, basename="test-category")
router.register(r"tests", DiagnosticTestViewSet, basename="diagnostic-test")
router.register(r"orders", TestOrderViewSet, basename="test-order")
router.register(r"order-items", TestOrderItemViewSet, basename="test-order-item")
router.register(r"reports", DiagnosticReportViewSet, basename="diagnostic-report")

urlpatterns = [
    path("", include(router.urls)),
]