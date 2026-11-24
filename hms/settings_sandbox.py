"""
Django sandbox settings for HMS project.

Used exclusively for Phase 1 migration validation and automated testing
against the disposable test database 'hms_disposable_val'.
NEVER points to or modifies 'mydatabase'.
"""

from pathlib import Path
from copy import deepcopy

from .settings import *

# Explicitly isolate the database to the disposable test database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "hms_disposable_val",
        "USER": "admin",
        "PASSWORD": "admin123",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

# Add apps.core before django.contrib.admin to guarantee proper swappable resolution
INSTALLED_APPS = [
    "apps.core.apps.CoreConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "apps.hospitals.apps.HospitalsConfig",
    "apps.accounting.apps.AccountingConfig",
    "apps.clinic.apps.ClinicConfig",
    "apps.patients.apps.PatientsConfig",
    "apps.doctors",
    "apps.pharmacy",
    "apps.diagnostic.apps.DiagnosticConfig",

    "rest_framework",
    "django_filters",
]

# Set Custom User Model for sandbox validation
AUTH_USER_MODEL = "core.User"

# Register Custom Authentication Backend supporting Email & Phone
AUTHENTICATION_BACKENDS = [
    "apps.core.backends.EmailOrPhoneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Set root urlconf for sandbox if needed or default urls
ROOT_URLCONF = "hms.urls_sandbox"
