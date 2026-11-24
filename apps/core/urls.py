from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.core.views import (
    LoginView,
    LogoutView,
    UserProfileView,
    PasswordChangeView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    DepartmentViewSet,
    EmployeeViewSet,
)

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"employees", EmployeeViewSet, basename="employee")

urlpatterns = [
    # Authentication Endpoints
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", UserProfileView.as_view(), name="auth-me"),
    path("auth/password/change/", PasswordChangeView.as_view(), name="auth-password-change"),
    path("auth/password/reset/request/", PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("auth/password/reset/confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),

    # Department & Employee ViewSet routes
    path("", include(router.urls)),
]
