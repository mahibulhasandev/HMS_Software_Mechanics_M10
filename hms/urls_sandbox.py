from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/core/", include("apps.core.urls")),
    path("api/", include("apps.patients.urls")),
    path("api/", include("apps.clinic.urls")),
    path("api/diagnostic/", include("apps.diagnostic.urls")),
]
