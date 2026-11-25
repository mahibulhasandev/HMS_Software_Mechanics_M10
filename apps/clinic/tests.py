import uuid
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.doctors.models import Doctor, DoctorDepartment
from apps.hospitals.models import Hospital
from apps.patients.models import Patient, PatientVisit
from apps.clinic.models import (
    Appointment,
    Consultation,
    Diagnosis,
    DoctorSchedule,
    Prescription,
    PrescriptionItem,
)


class ClinicAPITests(APITestCase):
    def setUp(self):
        self.hospital = Hospital.objects.create(
            registration_number="REG-CLN-001",
            name="Adabor Care Hospital",
            address="Adabor, Dhaka-1207",
            phone="+8801700000010",
            email="clinic@adaborcare.com",
        )
        self.department = DoctorDepartment.objects.create(
            hospital=self.hospital,
            name="General Medicine",
        )
        self.doctor = Doctor.objects.create(
            hospital=self.hospital,
            department=self.department,
            doctor_code="DOC-101",
            first_name="Dr. Tariq",
            last_name="Hasan",
            gender=Doctor.Gender.MALE,
            phone="+8801711111122",
        )
        self.patient = Patient.objects.create(
            hospital=self.hospital,
            patient_number="PAT-001",
            first_name="Rafi",
            last_name="Ahmed",
            gender=Patient.Gender.MALE,
            phone="+8801733333333",
        )
        self.visit = PatientVisit.objects.create(
            hospital=self.hospital,
            patient=self.patient,
            visit_number="VIS-001",
            visit_date=timezone.now(),
        )
        self.schedule = DoctorSchedule.objects.create(
            hospital=self.hospital,
            doctor=self.doctor,
            weekday=DoctorSchedule.Weekday.MONDAY,
            start_time="09:00:00",
            end_time="13:00:00",
            slot_minutes=15,
            max_patients=16,
            valid_from="2026-11-01",
        )
        self.appointment = Appointment.objects.create(
            hospital=self.hospital,
            patient=self.patient,
            doctor=self.doctor,
            patient_visit=self.visit,
            appointment_date="2026-11-30",
            appointment_time="10:00:00",
        )
        self.consultation = Consultation.objects.create(
            hospital=self.hospital,
            patient_visit=self.visit,
            doctor=self.doctor,
            appointment=self.appointment,
            complaints="Fever and headache",
            advice="Take rest and drink fluids",
        )

    def test_schedule_validation_and_listing(self):
        url = reverse("doctor-schedule-list")
        get_res = self.client.get(url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_res.data), 1)

        bad_res = self.client.post(
            url,
            {
                "hospital": str(self.hospital.id),
                "doctor": str(self.doctor.id),
                "weekday": 2,
                "start_time": "14:00:00",
                "end_time": "12:00:00",
                "slot_minutes": 15,
                "max_patients": 10,
                "valid_from": "2026-11-01",
            },
            format="json",
        )
        self.assertEqual(bad_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_appointment_create_and_status_update(self):
        url = reverse("appointment-list")
        create_res = self.client.post(
            url,
            {
                "hospital": str(self.hospital.id),
                "patient": str(self.patient.id),
                "doctor": str(self.doctor.id),
                "appointment_date": "2026-12-01",
                "appointment_time": "11:30:00",
                "booking_source": "online",
                "reason": "Follow up checkup",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)

        detail_url = reverse("appointment-detail", args=[self.appointment.id])
        patch_res = self.client.patch(
            detail_url,
            {"status": Appointment.Status.COMPLETED},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["status"], Appointment.Status.COMPLETED)

    def test_consultation_diagnosis_and_prescription_flow(self):
        diag_url = reverse("diagnosis-list")
        diag_res = self.client.post(
            diag_url,
            {
                "hospital": str(self.hospital.id),
                "consultation": str(self.consultation.id),
                "diagnosis_name": "Viral Fever",
                "icd_code": "B34.9",
                "diagnosis_type": Diagnosis.DiagnosisType.PRIMARY,
            },
            format="json",
        )
        self.assertEqual(diag_res.status_code, status.HTTP_201_CREATED)

        presc_url = reverse("prescription-list")
        presc_res = self.client.post(
            presc_url,
            {
                "hospital": str(self.hospital.id),
                "consultation": str(self.consultation.id),
                "notes": "After meal",
            },
            format="json",
        )
        self.assertEqual(presc_res.status_code, status.HTTP_201_CREATED)
        presc_id = presc_res.data["id"]

        item_url = reverse("prescription-item-list")
        item_res = self.client.post(
            item_url,
            {
                "hospital": str(self.hospital.id),
                "prescription": presc_id,
                "medicine_id": str(uuid.uuid4()),
                "dosage": "500mg",
                "frequency": "1+0+1",
                "duration_days": 5,
                "quantity": 10,
                "instructions": "Take after food",
            },
            format="json",
        )
        self.assertEqual(item_res.status_code, status.HTTP_201_CREATED)

        detail_res = self.client.get(reverse("prescription-detail", args=[presc_id]))
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail_res.data["items"]), 1)
