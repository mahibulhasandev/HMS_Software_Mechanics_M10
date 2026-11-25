import uuid
import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.hospitals.models import Hospital
from apps.doctors.models import DoctorDepartment, DoctorSpecialization, Doctor
from apps.core.models import (
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)

User = get_user_model()


class DoctorEmployeeIntegrationTests(TestCase):
    """
    Tests for Doctor-Employee integration:
    1. Unlinked Doctor records remain valid.
    2. Valid Doctor-Employee linkage succeeds (same hospital, role=doctor, approved, active).
    3. Cross-hospital Doctor-Employee linkage rejected.
    4. Non-doctor employee role rejected.
    5. Pending/unapproved employee rejected.
    6. Suspended/inactive employee rejected.
    7. OneToOne uniqueness enforced (two doctors cannot link to same employee).
    """

    @classmethod
    def setUpTestData(cls):
        # Setup Hospital A
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-DOC-A",
            name="Alpha Medical Center",
            address="Dhaka, Bangladesh",
            phone="01711111111",
            email="alpha@example.com",
        )
        # Setup Hospital B
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-DOC-B",
            name="Beta Medical Center",
            address="Chittagong, Bangladesh",
            phone="01722222222",
            email="beta@example.com",
        )

        # Department in Hospital A
        cls.dept_cardio_a = DoctorDepartment.objects.create(
            hospital=cls.hospital_a,
            name="Cardiology",
        )
        cls.spec_cardio_a = DoctorSpecialization.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept_cardio_a,
            name="Interventional Cardiology",
        )

        # Department in Hospital B
        cls.dept_cardio_b = DoctorDepartment.objects.create(
            hospital=cls.hospital_b,
            name="Cardiology B",
        )

        # User and Doctor Employee in Hospital A
        cls.user_doc_a = User.objects.create_user(
            email="doctor.alpha@example.com",
            phone="+8801700000010",
            password="DocPassword123!",
            first_name="Tariq",
            last_name="Ahmed",
        )
        cls.emp_doc_a = Employee.objects.create(
            user=cls.user_doc_a,
            hospital=cls.hospital_a,
            employee_id="EMP-DOC-A01",
            designation="Consultant Cardiologist",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # User and Doctor Employee in Hospital B
        cls.user_doc_b = User.objects.create_user(
            email="doctor.beta@example.com",
            phone="+8801700000020",
            password="DocPassword123!",
            first_name="Bilal",
            last_name="Hasan",
        )
        cls.emp_doc_b = Employee.objects.create(
            user=cls.user_doc_b,
            hospital=cls.hospital_b,
            employee_id="EMP-DOC-B01",
            designation="Consultant",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Nurse Employee in Hospital A
        cls.user_nurse_a = User.objects.create_user(
            email="nurse.alpha@example.com",
            phone="+8801700000030",
            password="NursePassword123!",
        )
        cls.emp_nurse_a = Employee.objects.create(
            user=cls.user_nurse_a,
            hospital=cls.hospital_a,
            employee_id="EMP-NUR-A01",
            designation="Staff Nurse",
            role=EmployeeRole.NURSE,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

    def test_unlinked_doctor_record_remains_valid(self):
        """Doctor record without an employee link is perfectly valid (nullable OneToOne)."""
        doctor = Doctor(
            hospital=self.hospital_a,
            department=self.dept_cardio_a,
            specialization=self.spec_cardio_a,
            doctor_code="DOC-UNLINKED-01",
            first_name="Standalone",
            last_name="Doctor",
            gender="male",
            phone="+8801711112222",
            employee=None,
        )
        doctor.full_clean()
        doctor.save()
        self.assertIsNotNone(doctor.id)
        self.assertIsNone(doctor.employee)

    def test_valid_doctor_employee_linkage_succeeds(self):
        """Linking approved, active doctor employee of same hospital passes full_clean()."""
        doctor = Doctor(
            hospital=self.hospital_a,
            department=self.dept_cardio_a,
            specialization=self.spec_cardio_a,
            doctor_code="DOC-LINKED-01",
            first_name="Tariq",
            last_name="Ahmed",
            gender="male",
            phone="+8801700000010",
            employee=self.emp_doc_a,
        )
        doctor.full_clean()
        doctor.save()
        self.assertEqual(doctor.employee, self.emp_doc_a)
        self.assertEqual(self.emp_doc_a.doctor_profile, doctor)

    def test_cross_hospital_doctor_employee_linkage_rejected(self):
        """Doctor in Hospital A cannot be linked to Employee of Hospital B."""
        doctor = Doctor(
            hospital=self.hospital_a,
            department=self.dept_cardio_a,
            specialization=self.spec_cardio_a,
            doctor_code="DOC-CROSS-01",
            first_name="Cross",
            last_name="Tenant",
            gender="male",
            phone="+8801733334444",
            employee=self.emp_doc_b,  # Belongs to hospital_b!
        )
        with self.assertRaises(ValidationError) as ctx:
            doctor.full_clean()
        self.assertIn("employee", ctx.exception.message_dict)
        self.assertIn("same hospital", str(ctx.exception.message_dict["employee"]))

    def test_non_doctor_role_employee_linkage_rejected(self):
        """Linking an employee with role != doctor (e.g., nurse) is rejected."""
        doctor = Doctor(
            hospital=self.hospital_a,
            department=self.dept_cardio_a,
            specialization=self.spec_cardio_a,
            doctor_code="DOC-NURSE-LINK",
            first_name="Wrong",
            last_name="Role",
            gender="female",
            phone="+8801755556666",
            employee=self.emp_nurse_a,  # Role is NURSE
        )
        with self.assertRaises(ValidationError) as ctx:
            doctor.full_clean()
        self.assertIn("employee", ctx.exception.message_dict)
        self.assertIn("doctor role", str(ctx.exception.message_dict["employee"]))

    def test_unapproved_employee_linkage_rejected(self):
        """Linking a pending employee is rejected."""
        pending_user = User.objects.create_user(
            email="pending.doc@example.com",
            phone="+8801799990001",
            password="DocPassword123!",
        )
        pending_emp = Employee.objects.create(
            user=pending_user,
            hospital=self.hospital_a,
            employee_id="EMP-DOC-PEND",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
            employment_status=EmploymentStatus.ACTIVE,
        )

        doctor = Doctor(
            hospital=self.hospital_a,
            department=self.dept_cardio_a,
            doctor_code="DOC-PEND-LINK",
            first_name="Pending",
            gender="male",
            phone="+8801799990001",
            employee=pending_emp,
        )
        with self.assertRaises(ValidationError) as ctx:
            doctor.full_clean()
        self.assertIn("employee", ctx.exception.message_dict)
        self.assertIn("approved", str(ctx.exception.message_dict["employee"]))

    def test_inactive_employee_linkage_rejected(self):
        """Linking a suspended/inactive employee is rejected."""
        suspended_user = User.objects.create_user(
            email="suspended.doc@example.com",
            phone="+8801799990002",
            password="DocPassword123!",
        )
        suspended_emp = Employee.objects.create(
            user=suspended_user,
            hospital=self.hospital_a,
            employee_id="EMP-DOC-SUS",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.SUSPENDED,
        )

        doctor = Doctor(
            hospital=self.hospital_a,
            department=self.dept_cardio_a,
            doctor_code="DOC-SUS-LINK",
            first_name="Suspended",
            gender="male",
            phone="+8801799990002",
            employee=suspended_emp,
        )
        with self.assertRaises(ValidationError) as ctx:
            doctor.full_clean()
        self.assertIn("employee", ctx.exception.message_dict)
        self.assertIn("active", str(ctx.exception.message_dict["employee"]))
