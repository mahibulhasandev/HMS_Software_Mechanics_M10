import uuid
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospitals.models import Hospital
from .models import Doctor


class DoctorAPITests(APITestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(
            registration_number="REG-HMS-001",
            name="Central City Hospital",
            address="Adabor, Dhaka-1207",
            phone="01700000000",
            email="info@centralhospital.test",
        )
        self.doctor = Doctor.objects.create(
            hospital=self.hospital,
            employee_id=uuid.uuid4(),
            employee_type="doctor",
            license_number="BMDC-1001",
            specialization="Cardiology",
            consultation_fee=Decimal("1000.00"),
        )
        self.list_url = reverse("doctor-list")

    def test_list_doctors(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["license_number"], "BMDC-1001")

    def test_create_doctor(self):
        payload = {
            "hospital": str(self.hospital.id),
            "employee_id": str(uuid.uuid4()),
            "employee_type": "doctor",
            "license_number": "BMDC-1002",
            "specialization": "Neurology",
            "consultation_fee": "1200.00",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Doctor.objects.count(), 2)

    def test_create_doctor_negative_fee_fails(self):
        payload = {
            "hospital": str(self.hospital.id),
            "employee_id": str(uuid.uuid4()),
            "employee_type": "doctor",
            "license_number": "BMDC-1003",
            "specialization": "Dermatology",
            "consultation_fee": "-50.00",
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_doctors_by_specialization(self):
        response = self.client.get(self.list_url, {"specialization": "Cardio"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_update_and_delete_doctor(self):
        detail_url = reverse("doctor-detail", args=[self.doctor.id])
        patch_res = self.client.patch(
            detail_url, {"consultation_fee": "1500.00"}, format="json"
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["consultation_fee"], "1500.00")

        delete_res = self.client.delete(detail_url)
        self.assertEqual(delete_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Doctor.objects.count(), 0)