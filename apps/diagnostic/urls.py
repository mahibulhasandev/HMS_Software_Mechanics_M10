from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DiagnosticReportViewSet,
    DiagnosticTestViewSet,
    TestCategoryViewSet,
    TestOrderItemViewSet,
    TestOrderViewSet,
    TestResultViewSet,
)

router = DefaultRouter()
router.register(r"test-categories", TestCategoryViewSet, basename="test-category")
router.register(r"diagnostic-tests", DiagnosticTestViewSet, basename="diagnostic-test")
router.register(r"test-orders", TestOrderViewSet, basename="test-order")
router.register(r"test-order-items", TestOrderItemViewSet, basename="test-order-item")
router.register(r"test-results", TestResultViewSet, basename="test-result")
router.register(r"diagnostic-reports", DiagnosticReportViewSet, basename="diagnostic-report")

urlpatterns = [
    path("", include(router.urls)),
]