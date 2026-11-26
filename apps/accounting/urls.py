from django.urls import path

from .api_views import AccountListAPIView

urlpatterns = [
    path("accounts/", AccountListAPIView.as_view(), name="accounting-accounts"),
]
