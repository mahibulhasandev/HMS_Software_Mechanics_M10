
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospitals.models import Hospital
from apps.patients.models import Patient, PatientVisit


class PatientAPITests(APITestCase):

    def setUp(self):
        self.hospital = Hospital.objects.create(
            registration_number="HOSP-TEST-001",
            name="Test Hospital",
            address="Dhaka, Bangladesh",
            phone="01700000000",
            email="testhospital@example.com",
        )

        self.patient_data = {
            "hospital": str(self.hospital.id),
            "patient_number": "PAT-TEST-001",
            "first_name": "Rahim",
            "last_name": "Ahmed",
            "date_of_birth": "2000-05-15",
            "gender": "male",
            "blood_group": "B+",
            "phone": "01712345678",
            "email": "rahim@example.com",
            "address": "Dhaka, Bangladesh",
            "emergency_contact_name": "Karim Ahmed",
            "emergency_contact_phone": "01812345678",
            "status": "active",
        }

        self.patient = Patient.objects.create(
            hospital=self.hospital,
            patient_number="PAT-EXISTING",
            first_name="Existing",
            last_name="Patient",
            date_of_birth="1999-01-01",
            gender="male",
            phone="01900000000",
            status="active",
        )

    def test_create_patient(self):
        url = reverse("patient-list")

        response = self.client.post(
            url,
            self.patient_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            Patient.objects.filter(
                patient_number="PAT-TEST-001"
            ).exists()
        )

    def test_list_patients(self):
        url = reverse("patient-list")

        response = self.client.get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertGreaterEqual(len(response.data), 1)

    def test_update_patient(self):
        url = reverse(
            "patient-detail",
            args=[self.patient.id],
        )

        response = self.client.patch(
            url,
            {
                "first_name": "Mahmud",
                "last_name": "Rahman",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.patient.refresh_from_db()

        self.assertEqual(
            self.patient.first_name,
            "Mahmud",
        )

    def test_create_patient_visit(self):
        url = reverse("patient-visit-list")

        visit_data = {
            "hospital": str(self.hospital.id),
            "patient": str(self.patient.id),
            "visit_number": "VIS-TEST-001",
            "visit_type": "opd",
            "visit_date": timezone.now().isoformat(),
            "chief_complaint": "Fever",
            "notes": "Automated API test",
            "status": "registered",
        }

        response = self.client.post(
            url,
            visit_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertTrue(
            PatientVisit.objects.filter(
                visit_number="VIS-TEST-001",
                patient=self.patient,
            ).exists()
        )

    def test_patient_cannot_be_deleted_with_visits(self):
        PatientVisit.objects.create(
            hospital=self.hospital,
            patient=self.patient,
            visit_number="VIS-PROTECT-001",
            visit_type="opd",
            visit_date=timezone.now(),
            status="registered",
        )

        url = reverse(
            "patient-detail",
            args=[self.patient.id],
        )

        response = self.client.delete(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertTrue(
            Patient.objects.filter(
                id=self.patient.id
            ).exists()
        )

    def test_visit_rejects_patient_from_another_hospital(self):
        another_hospital = Hospital.objects.create(
            registration_number="HOSP-TEST-002",
            name="Another Test Hospital",
            address="Sylhet, Bangladesh",
            phone="01800000000",
            email="another@example.com",
        )

        url = reverse("patient-visit-list")

        visit_data = {
            "hospital": str(another_hospital.id),
            "patient": str(self.patient.id),
            "visit_number": "VIS-INVALID-001",
            "visit_type": "opd",
            "visit_date": timezone.now().isoformat(),
            "chief_complaint": "Fever",
            "status": "registered",
        }

        response = self.client.post(
            url,
            visit_data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            PatientVisit.objects.filter(
                visit_number="VIS-INVALID-001"
            ).exists()
        )
