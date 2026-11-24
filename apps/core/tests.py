import uuid
import datetime
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.hospitals.models import Hospital
from apps.core.models import (
    Department,
    DepartmentType,
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)

User = get_user_model()


class CoreModelTests(TestCase):
    """
    Tests for User, Department, and Employee models in apps.core.
    Validated using hms.settings_sandbox with AUTH_USER_MODEL = 'core.User'.
    """

    @classmethod
    def setUpTestData(cls):
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-CORE-A",
            name="General Hospital Alpha",
            address="Dhaka, Bangladesh",
            phone="01700000001",
            email="alpha@hospital.com",
        )
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-CORE-B",
            name="City Hospital Beta",
            address="Chittagong, Bangladesh",
            phone="01700000002",
            email="beta@hospital.com",
        )

        cls.dept_cardiology = Department.objects.create(
            hospital=cls.hospital_a,
            name="Cardiology",
            code="CARD-01",
            department_type=DepartmentType.CLINICAL,
        )
        cls.dept_nursing = Department.objects.create(
            hospital=cls.hospital_a,
            name="Nursing",
            code="NUR-01",
            department_type=DepartmentType.NURSING,
        )
        cls.dept_beta_admin = Department.objects.create(
            hospital=cls.hospital_b,
            name="Administration",
            code="ADM-01",
            department_type=DepartmentType.ADMINISTRATIVE,
        )

    # --------------------------------------------------------------------------
    # 1. USER & USERMANAGER TESTS
    # --------------------------------------------------------------------------

    def test_create_user_with_email(self):
        """User can be created with email and password; PK is UUID."""
        user = User.objects.create_user(
            email="doctor.rahim@example.com",
            password="StrongPassword123!",
            first_name="Rahim",
            last_name="Uddin",
        )
        self.assertIsInstance(user.id, uuid.UUID)
        self.assertEqual(user.email, "doctor.rahim@example.com")
        self.assertTrue(user.check_password("StrongPassword123!"))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.full_name, "Rahim Uddin")

    def test_create_user_with_phone(self):
        """User can be created with phone number as primary identifier."""
        user = User.objects.create_user(
            phone="+8801712345678",
            password="PhonePassword123!",
        )
        self.assertIsInstance(user.id, uuid.UUID)
        self.assertEqual(user.phone, "+8801712345678")
        self.assertIsNone(user.email)
        self.assertTrue(user.check_password("PhonePassword123!"))

    def test_create_superuser(self):
        """Superuser creation sets is_staff=True and is_superuser=True."""
        admin = User.objects.create_superuser(
            email="admin.super@hms.com",
            password="AdminPassword123!",
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_active)

    def test_user_requires_email_or_phone(self):
        """UserManager must reject creation if neither email nor phone is given."""
        with self.assertRaises(ValueError):
            User.objects.create_user(password="Pass1234")

    # --------------------------------------------------------------------------
    # 2. DEPARTMENT CONSTRAINTS
    # --------------------------------------------------------------------------

    def test_department_unique_per_hospital(self):
        """Duplicate department names within the same hospital are rejected."""
        with self.assertRaises(IntegrityError):
            Department.objects.create(
                hospital=self.hospital_a,
                name="Cardiology",  # Already exists in hospital_a
                department_type=DepartmentType.CLINICAL,
            )

    def test_same_department_name_different_hospitals_allowed(self):
        """Different hospitals can have departments with the same name."""
        dept_beta = Department.objects.create(
            hospital=self.hospital_b,
            name="Cardiology",
            department_type=DepartmentType.CLINICAL,
        )
        self.assertIsNotNone(dept_beta.id)

    # --------------------------------------------------------------------------
    # 3. EMPLOYEE & MULTI-HOSPITAL RELATIONSHIP TESTS
    # --------------------------------------------------------------------------

    def test_single_user_multiple_hospital_employment(self):
        """One User can legitimately hold Employee records across different hospitals."""
        doctor_user = User.objects.create_user(
            email="multi.doctor@example.com",
            password="DocPassword123!",
            first_name="Multihospital",
            last_name="Doctor",
        )

        # Employment at Hospital Alpha
        emp_alpha = Employee.objects.create(
            user=doctor_user,
            hospital=self.hospital_a,
            department=self.dept_cardiology,
            employee_id="DOC-ALPHA-01",
            designation="Senior Consultant",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
        )

        # Employment at Hospital Beta
        emp_beta = Employee.objects.create(
            user=doctor_user,
            hospital=self.hospital_b,
            department=self.dept_beta_admin,
            employee_id="DOC-BETA-01",
            designation="Visiting Specialist",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
        )

        self.assertNotEqual(emp_alpha.hospital_id, emp_beta.hospital_id)
        self.assertEqual(doctor_user.employee_profiles.count(), 2)

    def test_duplicate_employee_per_hospital_prevented(self):
        """A User cannot have two Employee records in the same Hospital."""
        nurse_user = User.objects.create_user(
            email="nurse.fatima@example.com",
            password="NursePassword123!",
        )

        Employee.objects.create(
            user=nurse_user,
            hospital=self.hospital_a,
            department=self.dept_nursing,
            employee_id="NUR-A-01",
            designation="Staff Nurse",
            role=EmployeeRole.NURSE,
        )

        # Attempting second employee record in hospital_a
        with self.assertRaises(IntegrityError):
            Employee.objects.create(
                user=nurse_user,
                hospital=self.hospital_a,
                department=self.dept_nursing,
                employee_id="NUR-A-02",
                designation="Nurse Supervisor",
                role=EmployeeRole.NURSE,
            )

    def test_employee_id_unique_per_hospital(self):
        """Two employees cannot share the same employee_id within the same hospital."""
        user1 = User.objects.create_user(email="staff1@example.com", password="P1")
        user2 = User.objects.create_user(email="staff2@example.com", password="P2")

        Employee.objects.create(
            user=user1,
            hospital=self.hospital_a,
            department=self.dept_nursing,
            employee_id="STAFF-A-100",
            role=EmployeeRole.GENERAL_STAFF,
        )

        with self.assertRaises(IntegrityError):
            Employee.objects.create(
                user=user2,
                hospital=self.hospital_a,
                department=self.dept_nursing,
                employee_id="STAFF-A-100",  # Duplicate ID in hospital_a
                role=EmployeeRole.GENERAL_STAFF,
            )

    # --------------------------------------------------------------------------
    # 4. CROSS-TENANT CLEAN() VALIDATION
    # --------------------------------------------------------------------------

    def test_department_hospital_mismatch_rejected_in_clean(self):
        """clean() must reject an Employee assigned to a department belonging to another hospital."""
        user = User.objects.create_user(email="mismatch@example.com", password="P1")
        employee = Employee(
            user=user,
            hospital=self.hospital_a,
            department=self.dept_beta_admin,  # belongs to hospital_b!
            employee_id="EMP-MIS-01",
            role=EmployeeRole.GENERAL_STAFF,
        )
        with self.assertRaises(ValidationError) as ctx:
            employee.clean()
        self.assertIn("department", ctx.exception.message_dict)

    def test_approving_admin_hospital_mismatch_rejected(self):
        """clean() must reject an approving admin from a different hospital."""
        admin_b_user = User.objects.create_user(email="admin_b@example.com", password="P1")
        admin_b = Employee.objects.create(
            user=admin_b_user,
            hospital=self.hospital_b,
            department=self.dept_beta_admin,
            employee_id="ADM-B-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
        )

        user_a = User.objects.create_user(email="applicant_a@example.com", password="P2")
        applicant = Employee(
            user=user_a,
            hospital=self.hospital_a,
            department=self.dept_cardiology,
            employee_id="APP-A-01",
            approved_by=admin_b,  # belongs to hospital_b!
            approval_status=ApprovalStatus.APPROVED,
        )
        with self.assertRaises(ValidationError) as ctx:
            applicant.clean()
        self.assertIn("approved_by", ctx.exception.message_dict)

    def test_self_approval_rejected(self):
        """An employee cannot approve their own registration."""
        admin_user = User.objects.create_user(email="self_app@example.com", password="P1")
        emp = Employee.objects.create(
            user=admin_user,
            hospital=self.hospital_a,
            department=self.dept_nursing,
            employee_id="SELF-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
        )
        emp.approved_by = emp
        with self.assertRaises(ValidationError) as ctx:
            emp.clean()
        self.assertIn("approved_by", ctx.exception.message_dict)
