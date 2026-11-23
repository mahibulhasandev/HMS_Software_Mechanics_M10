import uuid
from datetime import datetime, timezone

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospitals.models import Hospital


class ClinicAPITests(APITestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(
            registration_number="REG-HMS-002",
            name="Metro Care Clinic",
            address="Gulshan, Dhaka",
            phone="01800000000",
            email="contact@metrocare.test",
        )
        self.doctor_id = str(uuid.uuid4())
        self.patient_id = str(uuid.uuid4())
        self.patient_visit_id = str(uuid.uuid4())
        self.medicine_id = str(uuid.uuid4())

    def test_create_and_list_doctor_schedule(self):
        url = reverse("doctor-schedule-list")
        payload = {
            "hospital": str(self.hospital.id),
            "doctor_id": self.doctor_id,
            "weekday": 1,
            "start_time": "09:00:00",
            "end_time": "13:00:00",
            "slot_minutes": 15,
            "max_patients": 16,
            "valid_from": "2026-11-01",
            "valid_to": "2026-12-31",
        }
        create_res = self.client.post(url, payload, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)

        list_res = self.client.get(url, {"doctor_id": self.doctor_id})
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

    def test_invalid_schedule_time_fails(self):
        url = reverse("doctor-schedule-list")
        payload = {
            "hospital": str(self.hospital.id),
            "doctor_id": self.doctor_id,
            "weekday": 2,
            "start_time": "14:00:00",
            "end_time": "12:00:00",
            "slot_minutes": 15,
            "max_patients": 10,
            "valid_from": "2026-11-01",
            "valid_to": "2026-12-31",
        }
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_and_filter_appointment(self):
        url = reverse("appointment-list")
        payload = {
            "hospital": str(self.hospital.id),
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "appointment_date": "2026-11-25",
            "start_time": "10:30:00",
            "status": "scheduled",
            "booking_source": "online",
        }
        create_res = self.client.post(url, payload, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)

        filter_res = self.client.get(url, {"status": "scheduled"})
        self.assertEqual(filter_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(filter_res.data), 1)

    def test_consultation_diagnosis_and_prescription_flow(self):
        consult_res = self.client.post(
            reverse("consultation-list"),
            {
                "hospital": str(self.hospital.id),
                "patient_visit_id": self.patient_visit_id,
                "doctor_id": self.doctor_id,
                "complaints": "Mild fever and headache",
                "examination_notes": "BP 120/80, Temp 100.2F",
                "advice": "Rest and hydration",
            },
            format="json",
        )
        self.assertEqual(consult_res.status_code, status.HTTP_201_CREATED)
        consultation_id = consult_res.data["id"]

        diag_res = self.client.post(
            reverse("diagnosis-list"),
            {
                "hospital": str(self.hospital.id),
                "consultation": consultation_id,
                "diagnosis_name": "Viral Fever",
                "icd_code": "B34.9",
                "diagnosis_type": "primary",
            },
            format="json",
        )
        self.assertEqual(diag_res.status_code, status.HTTP_201_CREATED)

        rx_res = self.client.post(
            reverse("prescription-list"),
            {
                "hospital": str(self.hospital.id),
                "consultation": consultation_id,
                "prescribed_at": datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc).isoformat(),
                "notes": "After meal",
            },
            format="json",
        )
        self.assertEqual(rx_res.status_code, status.HTTP_201_CREATED)
        prescription_id = rx_res.data["id"]

        item_res = self.client.post(
            reverse("prescription-item-list"),
            {
                "hospital": str(self.hospital.id),
                "prescription": prescription_id,
                "medicine_id": self.medicine_id,
                "dosage": "500mg",
                "frequency": "1+1+1",
                "duration_days": 5,
                "quantity": 15,
                "instructions": "Take with water",
            },
            format="json",
        )
        self.assertEqual(item_res.status_code, status.HTTP_201_CREATED)

        rx_detail = self.client.get(
            reverse("prescription-detail", args=[prescription_id])
        )
        self.assertEqual(rx_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(rx_detail.data["items"]), 1)
        self.assertEqual(rx_detail.data["items"][0]["dosage"], "500mg")
