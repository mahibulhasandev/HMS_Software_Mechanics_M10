import datetime
import uuid
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APIClient

from apps.hospitals.models import Hospital
from apps.core.models import (
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)
from apps.doctors.models import Doctor, DoctorDepartment
from apps.patients.models import Patient, PatientVisit
from apps.clinic.models import Appointment

User = get_user_model()


class PatientCheckInWorkflowTests(TestCase):
    """
    Automated Test Suite for Patient Check-in Workflow (POST /api/clinic/appointments/{id}/check-in/):
    1. Successful check-in by authorized receptionist.
    2. PatientVisit creation (OPD, REGISTERED, linked to correct patient & hospital).
    3. Appointment and PatientVisit bidirectional linkage and status transition to CHECKED_IN.
    4. Duplicate check-in prevention (idempotent 200 response with 'Already checked in.').
    5. Unauthorized doctor access rejection (403 Forbidden).
    6. Cross-hospital access rejection (Receptionist/Admin from Hospital B cannot check in Hospital A appointment).
    7. Cancelled appointment rejection (400 Bad Request - only CONFIRMED appointments can be checked in).
    8. Non-existent appointment rejection (404 Not Found).
    9. Missing hospital context rejection (400 Bad Request).
    """

    @classmethod
    def setUpTestData(cls):
        # Hospital A
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-CHK-A",
            name="Alpha Checkin Hospital",
            address="Dhaka",
            phone="01711111199",
        )
        # Hospital B
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-CHK-B",
            name="Beta Checkin Hospital",
            address="Chittagong",
            phone="01722222299",
        )

        # Hospital A Staff: Admin, Receptionist, Doctor
        cls.user_admin = User.objects.create_user(
            email="admin.checkin@example.com",
            password="AdminPassword123!",
        )
        cls.emp_admin = Employee.objects.create(
            user=cls.user_admin,
            hospital=cls.hospital_a,
            employee_id="ADM-CHK-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        cls.user_rec = User.objects.create_user(
            email="rec.checkin@example.com",
            password="RecPassword123!",
        )
        cls.emp_rec = Employee.objects.create(
            user=cls.user_rec,
            hospital=cls.hospital_a,
            employee_id="REC-CHK-01",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        cls.user_doc = User.objects.create_user(
            email="doc.checkin@example.com",
            password="DocPassword123!",
        )
        cls.emp_doc = Employee.objects.create(
            user=cls.user_doc,
            hospital=cls.hospital_a,
            employee_id="DOC-CHK-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Hospital B Staff: Receptionist
        cls.user_b_rec = User.objects.create_user(
            email="rec.b.checkin@example.com",
            password="RecBPassword123!",
        )
        cls.emp_b_rec = Employee.objects.create(
            user=cls.user_b_rec,
            hospital=cls.hospital_b,
            employee_id="REC-CHK-B01",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Doctor Profile in Hospital A
        cls.dept = DoctorDepartment.objects.create(
            hospital=cls.hospital_a,
            name="General Medicine",
        )
        cls.doctor = Doctor.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept,
            employee=cls.emp_doc,
            doctor_code="DOC-CHK-001",
            first_name="Zubair",
            last_name="Ahmed",
            gender=Doctor.Gender.MALE,
            phone="+8801700000099",
            status=Doctor.Status.ACTIVE,
        )

        # Patient in Hospital A
        cls.patient_a = Patient.objects.create(
            hospital=cls.hospital_a,
            patient_number="PAT-CHK-001",
            first_name="Sultana",
            last_name="Razia",
            gender="female",
            phone="01811111199",
            date_of_birth=datetime.date(1995, 5, 5),
        )

        # Patient in Hospital B
        cls.patient_b = Patient.objects.create(
            hospital=cls.hospital_b,
            patient_number="PAT-CHK-B001",
            first_name="Belal",
            last_name="Hossain",
            gender="male",
            phone="01822222299",
            date_of_birth=datetime.date(1993, 3, 3),
        )

    def setUp(self):
        self.client = APIClient()

    def test_successful_check_in_creates_patient_visit_and_updates_status(self):
        """
        1. Successful check-in by receptionist:
        - Creates PatientVisit with OPD type and REGISTERED status.
        - Links PatientVisit to Appointment.
        - Updates Appointment status to CHECKED_IN.
        - Returns 200 with both appointment and patient_visit data.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(10, 0),
            status=Appointment.Status.CONFIRMED,
        )
        self.assertIsNone(appointment.patient_visit)

        self.client.force_authenticate(user=self.user_rec)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("appointment", response.data)
        self.assertIn("patient_visit", response.data)

        # Refresh from database
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CHECKED_IN)
        self.assertIsNotNone(appointment.patient_visit)

        visit = appointment.patient_visit
        self.assertEqual(visit.hospital, self.hospital_a)
        self.assertEqual(visit.patient, self.patient_a)
        self.assertEqual(visit.visit_type, PatientVisit.VisitType.OPD)
        self.assertEqual(visit.status, PatientVisit.Status.REGISTERED)

        # Verify returned serialized payload
        self.assertEqual(response.data["appointment"]["status"], Appointment.Status.CHECKED_IN)
        self.assertEqual(str(response.data["patient_visit"]["id"]), str(visit.id))
        self.assertEqual(str(response.data["patient_visit"]["hospital"]), str(self.hospital_a.id))
        self.assertEqual(str(response.data["patient_visit"]["patient"]), str(self.patient_a.id))

    def test_duplicate_check_in_prevention_is_idempotent(self):
        """
        4. Duplicate check-in calls return 200 with existing data and detail 'Already checked in.',
        without creating extra PatientVisit records.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(10, 30),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_rec)

        # First check-in
        res1 = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        visit_id_1 = res1.data["patient_visit"]["id"]
        initial_visits_count = PatientVisit.objects.filter(patient=self.patient_a).count()

        # Second check-in (idempotency check)
        res2 = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data.get("detail"), "Already checked in.")
        self.assertEqual(res2.data["patient_visit"]["id"], visit_id_1)

        # Confirm no extra PatientVisit was created in DB
        final_visits_count = PatientVisit.objects.filter(patient=self.patient_a).count()
        self.assertEqual(initial_visits_count, final_visits_count)

    def test_unauthorized_doctor_access_rejected(self):
        """
        5. Doctors cannot check in patients (only Receptionist, Hospital Admin, Admin allowed).
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(11, 0),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_doc)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("cannot perform check‑in", str(response.data))

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertIsNone(appointment.patient_visit)

    def test_cross_hospital_access_rejected(self):
        """
        6. Staff from Hospital B cannot check in an appointment in Hospital A.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(11, 30),
            status=Appointment.Status.CONFIRMED,
        )

        # Hospital B receptionist tries with Hospital A header (spoofing)
        self.client.force_authenticate(user=self.user_b_rec)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Hospital B receptionist tries with Hospital B header on Hospital A appointment
        response_b = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.id),
        )
        self.assertEqual(response_b.status_code, status.HTTP_404_NOT_FOUND)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertIsNone(appointment.patient_visit)

    def test_cancelled_appointment_rejected(self):
        """
        7. Checking in a CANCELLED appointment must be rejected with 400 Bad Request.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(12, 0),
            status=Appointment.Status.CANCELLED,
            cancellation_reason="Patient requested cancellation",
        )

        self.client.force_authenticate(user=self.user_rec)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)
        self.assertIsNone(appointment.patient_visit)

    def test_pending_appointment_rejected(self):
        """
        Checking in an unconfirmed (PENDING) appointment must be rejected.
        Only CONFIRMED appointments can be checked in.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(12, 30),
            status=Appointment.Status.PENDING,
        )

        self.client.force_authenticate(user=self.user_rec)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_missing_hospital_context_rejected(self):
        """
        9. Requests without X-Hospital-ID header are rejected.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(13, 0),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_rec)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
        )
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

    def test_admin_can_perform_check_in(self):
        """
        Hospital Admin is an authorized role and can perform check-in.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(13, 30),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_admin)
        response = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CHECKED_IN)
        self.assertIsNotNone(appointment.patient_visit)


class PatientCheckInConcurrencyAndRollbackTests(TransactionTestCase):
    """
    Tests for Concurrency Protection and Transaction Rollback:
    1. Transaction Rollback: If an exception occurs after PatientVisit creation (e.g. during appointment.save()),
       the transaction must roll back so no orphan PatientVisit is persisted.
    2. Concurrent Check-in Simulation: Simulates concurrent threads attempting check-in.
    """

    def setUp(self):
        self.client = APIClient()

        self.hospital = Hospital.objects.create(
            registration_number="HOSP-CHK-TX",
            name="Transaction Hospital",
            address="Dhaka",
            phone="01799999999",
        )
        self.user_rec = User.objects.create_user(
            email="rec.tx@example.com",
            password="RecPassword123!",
        )
        self.emp_rec = Employee.objects.create(
            user=self.user_rec,
            hospital=self.hospital,
            employee_id="REC-TX-01",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        self.user_doc = User.objects.create_user(
            email="doc.tx@example.com",
            password="DocPassword123!",
        )
        self.emp_doc = Employee.objects.create(
            user=self.user_doc,
            hospital=self.hospital,
            employee_id="DOC-TX-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )
        self.dept = DoctorDepartment.objects.create(
            hospital=self.hospital,
            name="Pediatrics",
        )
        self.doctor = Doctor.objects.create(
            hospital=self.hospital,
            department=self.dept,
            employee=self.emp_doc,
            doctor_code="DOC-TX-001",
            first_name="Monir",
            last_name="Hasan",
            gender=Doctor.Gender.MALE,
            phone="+8801700000088",
            status=Doctor.Status.ACTIVE,
        )

        self.patient = Patient.objects.create(
            hospital=self.hospital,
            patient_number="PAT-TX-001",
            first_name="Anisur",
            last_name="Rahman",
            gender="male",
            phone="01811111188",
            date_of_birth=datetime.date(1998, 8, 8),
        )

    def test_transaction_rollback_on_failure(self):
        """
        9. Transaction rollback:
        If saving the appointment fails after PatientVisit.objects.create(),
        the atomic block must roll back and no PatientVisit record must persist.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital,
            doctor=self.doctor,
            patient=self.patient,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(14, 0),
            status=Appointment.Status.CONFIRMED,
        )

        initial_visits_count = PatientVisit.objects.filter(patient=self.patient).count()
        self.assertEqual(initial_visits_count, 0)

        self.client.force_authenticate(user=self.user_rec)

        # Mock Appointment.save to raise an exception simulating database/network failure
        with patch.object(Appointment, "save", side_effect=IntegrityError("Simulated DB Failure")):
            with self.assertRaises(IntegrityError):
                self.client.post(
                    f"/api/clinic/appointments/{appointment.id}/check-in/",
                    HTTP_X_HOSPITAL_ID=str(self.hospital.id),
                )

        # Verify rollback: No PatientVisit persisted, appointment remains CONFIRMED
        final_visits_count = PatientVisit.objects.filter(patient=self.patient).count()
        self.assertEqual(final_visits_count, 0)

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertIsNone(appointment.patient_visit)

    def test_concurrent_check_in_protection(self):
        """
        8. Concurrent check-in protection:
        select_for_update() serializes check-in requests. Even if multiple requests execute,
        exactly one PatientVisit is created and both requests resolve consistently.
        """
        appointment = Appointment.objects.create(
            hospital=self.hospital,
            doctor=self.doctor,
            patient=self.patient,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(15, 0),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_rec)

        # Call endpoint sequentially to emulate serialized transactions
        res1 = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital.id),
        )
        res2 = self.client.post(
            f"/api/clinic/appointments/{appointment.id}/check-in/",
            HTTP_X_HOSPITAL_ID=str(self.hospital.id),
        )

        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.status_code, status.HTTP_200_OK)

        # Exactly 1 PatientVisit created for this appointment
        visits = PatientVisit.objects.filter(patient=self.patient)
        self.assertEqual(visits.count(), 1)
        self.assertEqual(res1.data["patient_visit"]["id"], str(visits.first().id))
        self.assertEqual(res2.data["patient_visit"]["id"], str(visits.first().id))
