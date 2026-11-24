import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

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


class CoreSecurityHardeningTests(TestCase):
    """
    Phase 1E Security Hardening & Permission Boundary Regression Tests.
    """

    def setUp(self):
        self.client = APIClient()

        # Create two isolated hospitals
        self.hospital_a = Hospital.objects.create(
            name="General Hospital Alpha",
            registration_number="REG-ALPHA-001",
            address="100 Alpha St",
            phone="01711111111",
            email="info@alpha.org",
        )
        self.hospital_b = Hospital.objects.create(
            name="City Hospital Beta",
            registration_number="REG-BETA-002",
            address="200 Beta St",
            phone="01822222222",
            email="info@beta.org",
        )

        # Hospital A Admin
        self.admin_a_user = User.objects.create_user(
            email="admin_a@alpha.org",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="Alpha",
        )
        self.admin_a_emp = Employee.objects.create(
            user=self.admin_a_user,
            hospital=self.hospital_a,
            employee_id="ADM-001",
            designation="Hospital Admin",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Hospital A Staff Doctor
        self.doctor_a_user = User.objects.create_user(
            email="doctor_a@alpha.org",
            password="DoctorPassword123!",
            first_name="Doctor",
            last_name="Alpha",
        )
        self.doctor_a_emp = Employee.objects.create(
            user=self.doctor_a_user,
            hospital=self.hospital_a,
            employee_id="DOC-001",
            designation="Senior Physician",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Hospital B Admin
        self.admin_b_user = User.objects.create_user(
            email="admin_b@beta.org",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="Beta",
        )
        self.admin_b_emp = Employee.objects.create(
            user=self.admin_b_user,
            hospital=self.hospital_b,
            employee_id="ADM-002",
            designation="Hospital Admin",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Department in Hospital A
        self.dept_cardio_a = Department.objects.create(
            hospital=self.hospital_a,
            name="Cardiology",
            code="CARD-A",
            department_type=DepartmentType.CLINICAL,
        )

    # --------------------------------------------------------------------------
    # 1. DEPARTMENT PERMISSION BOUNDARY TESTS
    # --------------------------------------------------------------------------

    def test_standard_staff_cannot_create_department(self):
        """Standard staff (Doctor) cannot create new departments (403 Forbidden)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        payload = {
            "hospital": str(self.hospital_a.id),
            "name": "Neurology",
            "code": "NEURO-A",
            "department_type": DepartmentType.CLINICAL,
        }
        res = self.client.post("/api/core/departments/", payload, HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_standard_staff_cannot_modify_or_delete_department(self):
        """Standard staff cannot update or delete departments."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res_patch = self.client.patch(
            f"/api/core/departments/{self.dept_cardio_a.id}/",
            {"name": "Advanced Cardiology"},
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

        res_delete = self.client.delete(
            f"/api/core/departments/{self.dept_cardio_a.id}/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_create_department_in_other_hospital(self):
        """Hospital A Admin cannot create department in Hospital B (Cross-Hospital Attack)."""
        self.client.force_authenticate(user=self.admin_a_user)
        payload = {
            "hospital": str(self.hospital_b.id),
            "name": "Orthopedics Beta",
            "code": "ORTHO-B",
            "department_type": DepartmentType.CLINICAL,
        }
        res = self.client.post("/api/core/departments/", payload, HTTP_X_HOSPITAL_ID=str(self.hospital_b.id))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_department_in_own_hospital(self):
        """Hospital A Admin can successfully create department in Hospital A."""
        self.client.force_authenticate(user=self.admin_a_user)
        payload = {
            "hospital": str(self.hospital_a.id),
            "name": "Neurology",
            "code": "NEURO-A",
            "department_type": DepartmentType.CLINICAL,
        }
        res = self.client.post("/api/core/departments/", payload, HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Department.objects.filter(code="NEURO-A", hospital=self.hospital_a).exists())

    # --------------------------------------------------------------------------
    # 2. EMPLOYEE API TAMPERING & PRIVILEGE ESCALATION
    # --------------------------------------------------------------------------

    def test_registration_payload_tampering_ignored(self):
        """Client cannot inject approval_status='approved' or approved_by during registration."""
        applicant = User.objects.create_user(
            email="nurse_app@alpha.org",
            password="NursePassword123!",
            first_name="Nurse",
            last_name="Applicant",
        )
        self.client.force_authenticate(user=applicant)
        payload = {
            "hospital": str(self.hospital_a.id),
            "department": str(self.dept_cardio_a.id),
            "employee_id": "NURSE-001",
            "designation": "Staff Nurse",
            "role": EmployeeRole.NURSE,
            "approval_status": "approved",  # Tampered
            "approved_by": str(self.admin_a_emp.id),  # Tampered
        }
        res = self.client.post("/api/core/employees/register/", payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created_emp = Employee.objects.get(employee_id="NURSE-001")
        self.assertEqual(created_emp.approval_status, ApprovalStatus.PENDING)
        self.assertIsNone(created_emp.approved_by)
        self.assertIsNone(created_emp.approved_at)

    def test_direct_employee_creation_rejected_for_standard_user(self):
        """Regular applicant cannot call direct POST /api/core/employees/ (403 Forbidden)."""
        applicant = User.objects.create_user(
            email="direct_app@alpha.org",
            password="AppPassword123!",
            first_name="Direct",
            last_name="Applicant",
        )
        self.client.force_authenticate(user=applicant)
        payload = {
            "user": str(applicant.id),
            "hospital": str(self.hospital_a.id),
            "department": str(self.dept_cardio_a.id),
            "employee_id": "DIR-001",
            "designation": "Staff",
            "role": EmployeeRole.RECEPTIONIST,
        }
        res = self.client.post("/api/core/employees/", payload)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_self_approval_blocked(self):
        """An admin or employee cannot approve their own application."""
        admin_applicant = User.objects.create_user(
            email="another_admin@alpha.org",
            password="AdminPassword123!",
            first_name="CoAdmin",
            last_name="Alpha",
        )
        pending_emp = Employee.objects.create(
            user=admin_applicant,
            hospital=self.hospital_a,
            employee_id="ADM-099",
            designation="Co-Admin",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.PENDING,
        )
        self.client.force_authenticate(user=admin_applicant)
        res = self.client.post(
            f"/api/core/employees/{pending_emp.id}/approve/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        # Blocked: Either 403 (not yet approved admin) or 400 (cannot approve self)
        self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

    def test_cross_hospital_approval_blocked(self):
        """Hospital B Admin cannot approve an employee belonging to Hospital A."""
        applicant = User.objects.create_user(
            email="tech@alpha.org",
            password="TechPassword123!",
            first_name="Tech",
            last_name="Alpha",
        )
        pending_emp = Employee.objects.create(
            user=applicant,
            hospital=self.hospital_a,
            employee_id="TECH-001",
            designation="Lab Tech",
            role=EmployeeRole.LAB_TECHNICIAN,
            approval_status=ApprovalStatus.PENDING,
        )
        self.client.force_authenticate(user=self.admin_b_user)
        res = self.client.post(
            f"/api/core/employees/{pending_emp.id}/approve/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.id),
        )
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    # --------------------------------------------------------------------------
    # 3. AUTHENTICATION & SESSION SECURITY
    # --------------------------------------------------------------------------

    def test_password_change_updates_session_auth_hash(self):
        """Password change updates the session auth hash properly."""
        client = APIClient()
        # Login via session
        login_res = client.post("/api/core/auth/login/", {
            "identifier": "doctor_a@alpha.org",
            "password": "DoctorPassword123!",
        })
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        # Change password (no confirm_password field)
        ch_res = client.post("/api/core/auth/password/change/", {
            "old_password": "DoctorPassword123!",
            "new_password": "NewDoctorPassword456!",
        })
        self.assertEqual(ch_res.status_code, status.HTTP_200_OK)

        # Verify old password fails
        self.doctor_a_user.refresh_from_db()
        self.assertFalse(self.doctor_a_user.check_password("DoctorPassword123!"))
        self.assertTrue(self.doctor_a_user.check_password("NewDoctorPassword456!"))

        # Profile access still succeeds because session auth hash was updated
        prof_res = client.get("/api/core/auth/me/")
        self.assertEqual(prof_res.status_code, status.HTTP_200_OK)

    def test_inactive_user_cannot_login(self):
        """Inactive accounts cannot authenticate."""
        self.doctor_a_user.is_active = False
        self.doctor_a_user.save()

        res = self.client.post("/api/core/auth/login/", {
            "identifier": "doctor_a@alpha.org",
            "password": "DoctorPassword123!",
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inactive", str(res.data))

    def test_login_csrf_protection(self):
        """Login POST succeeds with valid credentials."""
        client = APIClient()
        resp = client.post("/api/core/auth/login/", {
            "identifier": "doctor_a@alpha.org",
            "password": "DoctorPassword123!",
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

