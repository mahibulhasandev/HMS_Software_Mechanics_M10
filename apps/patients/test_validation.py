import datetime
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.hospitals.models import Hospital
from apps.patients.models import Patient


class PatientValidationTests(TestCase):
    """
    Direct unit tests for Patient model validation, specifically testing
    the date_of_birth clean() validation fix.
    """

    @classmethod
    def setUpTestData(cls):
        cls.hospital = Hospital.objects.create(
            registration_number="HOSP-VAL-001",
            name="Validation Hospital",
            address="Dhaka, Bangladesh",
            phone="01700000000",
            email="validation@example.com",
        )

    def test_valid_past_date_of_birth(self):
        """Past date of birth must cleanly pass full_clean()."""
        patient = Patient(
            hospital=self.hospital,
            patient_number="PAT-PAST-01",
            first_name="Rahim",
            gender="male",
            phone="01711111111",
            date_of_birth=datetime.date(1995, 5, 20),
        )
        patient.full_clean()
        patient.save()
        self.assertIsNotNone(patient.id)

    def test_today_date_of_birth(self):
        """A newborn born today (timezone.localdate()) must cleanly pass full_clean()."""
        patient = Patient(
            hospital=self.hospital,
            patient_number="PAT-TODAY-01",
            first_name="Newborn",
            gender="female",
            phone="01722222222",
            date_of_birth=timezone.localdate(),
        )
        patient.full_clean()
        patient.save()
        self.assertIsNotNone(patient.id)

    def test_future_date_of_birth_rejected(self):
        """A future date of birth must raise ValidationError on clean() and full_clean()."""
        future_date = timezone.localdate() + datetime.timedelta(days=1)
        patient = Patient(
            hospital=self.hospital,
            patient_number="PAT-FUT-01",
            first_name="Future",
            gender="other",
            phone="01733333333",
            date_of_birth=future_date,
        )
        with self.assertRaises(ValidationError) as ctx:
            patient.full_clean()
        self.assertIn("date_of_birth", ctx.exception.message_dict)
        self.assertEqual(
            ctx.exception.message_dict["date_of_birth"],
            ["Date of birth cannot be in the future."],
        )

    def test_null_date_of_birth_allowed(self):
        """Null date of birth is permitted by schema and must pass validation."""
        patient = Patient(
            hospital=self.hospital,
            patient_number="PAT-NULL-01",
            first_name="Undated",
            gender="male",
            phone="01744444444",
            date_of_birth=None,
        )
        patient.full_clean()
        patient.save()
        self.assertIsNotNone(patient.id)
