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

    # --------------------------------------------------------------------------
    # 2. PATIENT SERIALIZER API DOB VALIDATION TESTS
    # --------------------------------------------------------------------------

    def test_serializer_accepts_valid_past_date_of_birth(self):
        """PatientSerializer must accept valid past date_of_birth."""
        from apps.patients.serializers import PatientSerializer

        payload = {
            "hospital": str(self.hospital.id),
            "patient_number": "PAT-SER-PAST",
            "first_name": "Rahim",
            "gender": "male",
            "phone": "01711111111",
            "date_of_birth": "1995-05-20",
        }
        serializer = PatientSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        patient = serializer.save()
        self.assertEqual(patient.date_of_birth, datetime.date(1995, 5, 20))

    def test_serializer_accepts_current_today_date_of_birth(self):
        """PatientSerializer must accept current today's date_of_birth."""
        from apps.patients.serializers import PatientSerializer

        today = timezone.localdate()
        payload = {
            "hospital": str(self.hospital.id),
            "patient_number": "PAT-SER-TODAY",
            "first_name": "Newborn",
            "gender": "female",
            "phone": "01722222222",
            "date_of_birth": str(today),
        }
        serializer = PatientSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        patient = serializer.save()
        self.assertEqual(patient.date_of_birth, today)

    def test_serializer_rejects_future_date_of_birth(self):
        """PatientSerializer must reject future date_of_birth and not create a record."""
        from apps.patients.serializers import PatientSerializer

        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        payload = {
            "hospital": str(self.hospital.id),
            "patient_number": "PAT-SER-FUT",
            "first_name": "FutureChild",
            "gender": "male",
            "phone": "01733333333",
            "date_of_birth": str(tomorrow),
        }
        serializer = PatientSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("date_of_birth", serializer.errors)
        self.assertEqual(
            serializer.errors["date_of_birth"],
            ["Date of birth cannot be in the future."],
        )
        self.assertFalse(Patient.objects.filter(patient_number="PAT-SER-FUT").exists())
