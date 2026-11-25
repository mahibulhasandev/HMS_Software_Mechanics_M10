from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospitals.models import Hospital
from .models import Doctor, DoctorDepartment, DoctorSpecialization


class DoctorsAPITests(APITestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(
            registration_number="REG-DOC-001",
            name="Dhaka Central Hospital",
            address="Adabor, Dhaka",
            phone="+8801700000000",
            email="info@dhakahospital.com",
        )
        self.other_hospital = Hospital.objects.create(
            registration_number="REG-DOC-002",
            name="Chittagong General Hospital",
            address="GEC, Chattogram",
            phone="+8801800000000",
            email="info@ctghospital.com",
        )
        self.department = DoctorDepartment.objects.create(
            hospital=self.hospital,
            name="Cardiology",
            description="Heart care department",
        )
        self.specialization = DoctorSpecialization.objects.create(
            hospital=self.hospital,
            department=self.department,
            name="Interventional Cardiology",
        )
        self.doctor = Doctor.objects.create(
            hospital=self.hospital,
            department=self.department,
            specialization=self.specialization,
            doctor_code="DOC-001",
            first_name="Dr. Arif",
            last_name="Rahman",
            gender=Doctor.Gender.MALE,
            phone="+8801711111111",
            consultation_fee=Decimal("1000.00"),
            follow_up_fee=Decimal("500.00"),
        )

    def test_list_and_create_doctor_department(self):
        url = reverse("doctor-department-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        create_res = self.client.post(
            url,
            {
                "hospital": str(self.hospital.id),
                "name": "Neurology",
                "description": "Brain and nerve care",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_res.data["name"], "Neurology")

    def test_specialization_cross_hospital_validation(self):
        url = reverse("doctor-specialization-list")
        response = self.client.post(
            url,
            {
                "hospital": str(self.other_hospital.id),
                "department": str(self.department.id),
                "name": "Mismatch Spec",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_filter_and_update_doctor(self):
        url = reverse("doctor-list")
        create_res = self.client.post(
            url,
            {
                "hospital": str(self.hospital.id),
                "department": str(self.department.id),
                "specialization": str(self.specialization.id),
                "doctor_code": "DOC-002",
                "first_name": "Dr. Nusrat",
                "last_name": "Jahan",
                "gender": "female",
                "phone": "+8801722222222",
                "consultation_fee": "1200.00",
                "follow_up_fee": "600.00",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_res.data["full_name"], "Dr. Nusrat Jahan")

        filter_res = self.client.get(url, {"search": "Nusrat"})
        self.assertEqual(filter_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(filter_res.data), 1)

        detail_url = reverse("doctor-detail", args=[self.doctor.id])
        patch_res = self.client.patch(
            detail_url,
            {"status": Doctor.Status.ON_LEAVE},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["status"], Doctor.Status.ON_LEAVE)

    def test_protected_department_delete_returns_400(self):
        url = reverse("doctor-department-detail", args=[self.department.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
