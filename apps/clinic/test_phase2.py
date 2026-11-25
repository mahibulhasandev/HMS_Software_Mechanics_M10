import datetime
import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
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
from apps.patients.models import Patient
from apps.clinic.models import DoctorSchedule, Appointment

User = get_user_model()


class ClinicPhase2SchedulingAndAppointmentTests(TestCase):
    """
    Phase 2: Scheduling & Appointment Engine Tests:
    1. DoctorSchedule CRUD & Permissions (Admin & Doctor can manage, Receptionist read-only).
    2. DoctorSchedule Invalid working hours rejection (end_time <= start_time).
    3. DoctorSchedule Overlap prevention (same weekday, same doctor, overlapping time/date).
    4. Doctor Availability endpoint (available-slots generation, capacity tracking, exclusion of booked slots).
    5. Appointment Creation via Receptionist and Admin.
    6. Doctor cannot book appointment for patients (only Receptionist/Admin).
    7. Concurrency / Double-booking prevention (exceeding max_patients capacity rejected).
    8. Doctor appointment visibility scoping (doctor only sees their assigned appointments).
    9. Cross-hospital access prevention (spoofed header or mismatch rejected).
    10. Invalid appointment status transitions rejected (e.g. Completed -> Pending, Cancelled -> Confirmed).
    """

    @classmethod
    def setUpTestData(cls):
        # Hospital A
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-CLN-P2A",
            name="Alpha Memorial Hospital",
            address="Dhaka",
            phone="01711111111",
        )
        # Hospital B
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-CLN-P2B",
            name="Beta General Hospital",
            address="Chittagong",
            phone="01722222222",
        )

        # Users and Employees for Hospital A
        cls.user_admin = User.objects.create_user(
            email="admin.p2@example.com",
            password="AdminPassword123!",
        )
        cls.emp_admin = Employee.objects.create(
            user=cls.user_admin,
            hospital=cls.hospital_a,
            employee_id="ADM-P2-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        cls.user_rec = User.objects.create_user(
            email="rec.p2@example.com",
            password="RecPassword123!",
        )
        cls.emp_rec = Employee.objects.create(
            user=cls.user_rec,
            hospital=cls.hospital_a,
            employee_id="REC-P2-01",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        cls.user_doc1 = User.objects.create_user(
            email="doc1.p2@example.com",
            password="DocPassword123!",
        )
        cls.emp_doc1 = Employee.objects.create(
            user=cls.user_doc1,
            hospital=cls.hospital_a,
            employee_id="DOC-P2-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        cls.user_doc2 = User.objects.create_user(
            email="doc2.p2@example.com",
            password="DocPassword123!",
        )
        cls.emp_doc2 = Employee.objects.create(
            user=cls.user_doc2,
            hospital=cls.hospital_a,
            employee_id="DOC-P2-02",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Hospital B User
        cls.user_b = User.objects.create_user(
            email="staff.b.p2@example.com",
            password="BetaPassword123!",
        )
        cls.emp_b = Employee.objects.create(
            user=cls.user_b,
            hospital=cls.hospital_b,
            employee_id="ADM-P2-B01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Doctor Departments & Doctors
        cls.dept_cardio = DoctorDepartment.objects.create(
            hospital=cls.hospital_a,
            name="Cardiology",
        )
        cls.doctor1 = Doctor.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept_cardio,
            employee=cls.emp_doc1,
            doctor_code="DOC-A-001",
            first_name="Rahim",
            last_name="Khan",
            gender=Doctor.Gender.MALE,
            phone="+8801700000001",
            status=Doctor.Status.ACTIVE,
        )
        cls.doctor2 = Doctor.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept_cardio,
            employee=cls.emp_doc2,
            doctor_code="DOC-A-002",
            first_name="Fatima",
            last_name="Ali",
            gender=Doctor.Gender.FEMALE,
            phone="+8801700000002",
            status=Doctor.Status.ACTIVE,
        )

        # Patient in Hospital A
        cls.patient1 = Patient.objects.create(
            hospital=cls.hospital_a,
            patient_number="PAT-P2-001",
            first_name="Karim",
            last_name="Uddin",
            gender="male",
            phone="01811111111",
            date_of_birth=datetime.date(1990, 1, 1),
        )
        # Patient in Hospital B
        cls.patient_b = Patient.objects.create(
            hospital=cls.hospital_b,
            patient_number="PAT-P2-B001",
            first_name="Hasan",
            last_name="Mahmud",
            gender="male",
            phone="01822222222",
            date_of_birth=datetime.date(1992, 2, 2),
        )

    def setUp(self):
        self.client = APIClient()

    # ==========================================================
    # 1. DOCTOR SCHEDULE CRUD & VALIDATION
    # ==========================================================

    def test_admin_can_create_doctor_schedule(self):
        """Hospital Admin can successfully create schedule for a hospital doctor."""
        self.client.force_authenticate(user=self.user_admin)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "weekday": 0,  # Monday
            "start_time": "09:00:00",
            "end_time": "12:00:00",
            "slot_minutes": 15,
            "max_patients": 1,
            "valid_from": str(timezone.localdate()),
            "is_available": True,
        }
        res = self.client.post(
            "/api/clinic/schedules/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["weekday"], 0)
        self.assertEqual(res.data["start_time"], "09:00:00")

    def test_doctor_can_create_own_schedule(self):
        """Doctor can create schedule for their own profile."""
        self.client.force_authenticate(user=self.user_doc1)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "weekday": 1,  # Tuesday
            "start_time": "14:00:00",
            "end_time": "17:00:00",
            "slot_minutes": 30,
            "max_patients": 2,
            "valid_from": str(timezone.localdate()),
            "is_available": True,
        }
        res = self.client.post(
            "/api/clinic/schedules/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

    def test_doctor_cannot_create_schedule_for_another_doctor(self):
        """Doctor 1 cannot create or tamper with schedule for Doctor 2."""
        self.client.force_authenticate(user=self.user_doc1)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor2.id),
            "weekday": 2,
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "slot_minutes": 15,
            "max_patients": 1,
            "valid_from": str(timezone.localdate()),
        }
        res = self.client.post(
            "/api/clinic/schedules/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_receptionist_cannot_create_schedule(self):
        """Receptionist has read-only access to doctor schedules; creation rejected."""
        self.client.force_authenticate(user=self.user_rec)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "weekday": 3,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "slot_minutes": 15,
            "valid_from": str(timezone.localdate()),
        }
        res = self.client.post(
            "/api/clinic/schedules/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_working_hours_rejected(self):
        """end_time <= start_time must be rejected with 400."""
        self.client.force_authenticate(user=self.user_admin)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "weekday": 4,
            "start_time": "16:00:00",
            "end_time": "10:00:00",  # Invalid
            "slot_minutes": 15,
            "valid_from": str(timezone.localdate()),
        }
        res = self.client.post(
            "/api/clinic/schedules/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_time", res.data)

    def test_schedule_overlap_prevention(self):
        """Creating an overlapping schedule for the same doctor and weekday is rejected."""
        # Create base schedule: Monday 09:00 - 13:00
        DoctorSchedule.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            weekday=0,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            slot_minutes=15,
            valid_from=timezone.localdate(),
            is_available=True,
        )

        self.client.force_authenticate(user=self.user_admin)
        # Try overlapping schedule: Monday 11:00 - 15:00
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "weekday": 0,
            "start_time": "11:00:00",
            "end_time": "15:00:00",
            "slot_minutes": 30,
            "valid_from": str(timezone.localdate()),
        }
        res = self.client.post(
            "/api/clinic/schedules/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", res.data)

    # ==========================================================
    # 2. DOCTOR AVAILABILITY ENGINE
    # ==========================================================

    def test_doctor_availability_slots_generation(self):
        """GET /api/clinic/doctors/{id}/available-slots/ returns correct available slots."""
        # Schedule: Monday (weekday=0) 10:00 - 11:00 (15 min slots = 4 slots: 10:00, 10:15, 10:30, 10:45)
        today = timezone.localdate()
        # Find next Monday
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_monday = today + datetime.timedelta(days=days_ahead)

        DoctorSchedule.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            weekday=0,
            start_time=datetime.time(10, 0),
            end_time=datetime.time(11, 0),
            slot_minutes=15,
            max_patients=1,
            valid_from=today,
            is_available=True,
        )

        # Pre-book 1 slot at 10:15
        Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient=self.patient1,
            appointment_date=next_monday,
            appointment_time=datetime.time(10, 15),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_rec)
        url = f"/api/clinic/doctors/{self.doctor1.id}/available-slots/?date={next_monday.isoformat()}"
        res = self.client.get(url, HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["total_available_slots"], 3)  # 4 slots - 1 booked = 3
        slot_times = [s["time"] for s in res.data["available_slots"]]
        self.assertIn("10:00:00", slot_times)
        self.assertNotIn("10:15:00", slot_times)  # Excluded because booked
        self.assertIn("10:30:00", slot_times)
        self.assertIn("10:45:00", slot_times)

    # ==========================================================
    # 3. APPOINTMENT BOOKING & CONCURRENCY
    # ==========================================================

    def test_receptionist_can_book_appointment(self):
        """Receptionist can book appointment for patient with active doctor."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        weekday = tomorrow.weekday()

        DoctorSchedule.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            weekday=weekday,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(12, 0),
            slot_minutes=15,
            max_patients=1,
            valid_from=timezone.localdate(),
        )

        self.client.force_authenticate(user=self.user_rec)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient": str(self.patient1.id),
            "appointment_date": str(tomorrow),
            "appointment_time": "09:15:00",
            "booking_source": "reception",
            "reason": "Chest pain",
        }
        res = self.client.post(
            "/api/clinic/appointments/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["status"], "pending")

    def test_doctor_cannot_book_appointment(self):
        """Doctor cannot book appointments (receptionist/admin duty)."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.client.force_authenticate(user=self.user_doc1)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient": str(self.patient1.id),
            "appointment_date": str(tomorrow),
            "appointment_time": "10:00:00",
        }
        res = self.client.post(
            "/api/clinic/appointments/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_double_booking_prevention(self):
        """Booking the same slot beyond schedule capacity is rejected."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        weekday = tomorrow.weekday()

        # Capacity max_patients = 1
        DoctorSchedule.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            weekday=weekday,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(12, 0),
            slot_minutes=15,
            max_patients=1,
            valid_from=timezone.localdate(),
        )

        # First booking succeeds
        Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient=self.patient1,
            appointment_date=tomorrow,
            appointment_time=datetime.time(9, 30),
            status=Appointment.Status.CONFIRMED,
        )

        # Second booking for same doctor/date/time must fail
        self.client.force_authenticate(user=self.user_rec)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient": str(self.patient1.id),
            "appointment_date": str(tomorrow),
            "appointment_time": "09:30:00",
            "booking_source": "phone",
        }
        res = self.client.post(
            "/api/clinic/appointments/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("appointment_time", res.data)

    def test_doctor_sees_only_assigned_appointments(self):
        """Doctor 1 sees only appointments assigned to Doctor 1, not Doctor 2."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)

        # Appointment for Doctor 1
        app1 = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient=self.patient1,
            appointment_date=tomorrow,
            appointment_time=datetime.time(10, 0),
            status=Appointment.Status.CONFIRMED,
        )
        # Appointment for Doctor 2
        app2 = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor2,
            patient=self.patient1,
            appointment_date=tomorrow,
            appointment_time=datetime.time(11, 0),
            status=Appointment.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.user_doc1)
        res = self.client.get(
            "/api/clinic/appointments/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", res.data) if isinstance(res.data, dict) else res.data
        ids = [item["id"] for item in results]
        self.assertIn(str(app1.id), ids)
        self.assertNotIn(str(app2.id), ids)

    def test_cross_hospital_access_prevention(self):
        """Staff from Hospital B cannot view or book appointments in Hospital A."""
        self.client.force_authenticate(user=self.user_b)
        res = self.client.get(
            "/api/clinic/appointments/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_hospital_patient_doctor_mismatch_rejected(self):
        """Booking appointment with Patient B in Hospital A is rejected."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.client.force_authenticate(user=self.user_admin)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient": str(self.patient_b.id),  # Belongs to Hospital B
            "appointment_date": str(tomorrow),
            "appointment_time": "10:00:00",
        }
        res = self.client.post(
            "/api/clinic/appointments/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("patient", res.data)

    def test_invalid_status_transitions_rejected(self):
        """Invalid transitions like completed -> pending or cancelled -> confirmed are rejected."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        app = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient=self.patient1,
            appointment_date=tomorrow,
            appointment_time=datetime.time(10, 0),
            status=Appointment.Status.COMPLETED,
        )

        self.client.force_authenticate(user=self.user_admin)
        # Attempt Completed -> Confirmed
        res = self.client.patch(
            f"/api/clinic/appointments/{app.id}/",
            data={"status": "confirmed"},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res.data)

    def test_cancellation_reason_required_on_cancel(self):
        """Cancelling an appointment requires cancellation_reason."""
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        app = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient=self.patient1,
            appointment_date=tomorrow,
            appointment_time=datetime.time(10, 0),
            status=Appointment.Status.PENDING,
        )

        self.client.force_authenticate(user=self.user_rec)
        res = self.client.patch(
            f"/api/clinic/appointments/{app.id}/",
            data={"status": "cancelled", "cancellation_reason": ""},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cancellation_reason", res.data)
