import uuid
import datetime
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

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


class AuthAndEmployeeAPITests(APITestCase):
    """
    Comprehensive API test suite for Phase 1C & 1D.
    Tests:
    - Email & Phone login
    - Inactive user rejection
    - Invalid credentials
    - Password change
    - Employee registration (Pending)
    - Admin approval & rejection
    - Self-approval rejection
    - Non-admin approval rejection
    - Cross-hospital isolation & duplicate registration rejection
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Setup two distinct hospital tenants
        cls.hospital_alpha = Hospital.objects.create(
            registration_number="HOSP-ALPHA-01",
            name="Alpha Medical Center",
            address="Dhaka, Bangladesh",
            phone="01711111111",
            email="info@alpha.com",
        )
        cls.hospital_beta = Hospital.objects.create(
            registration_number="HOSP-BETA-01",
            name="Beta Specialized Hospital",
            address="Sylhet, Bangladesh",
            phone="01722222222",
            email="info@beta.com",
        )

        # 2. Departments
        cls.dept_cardio = Department.objects.create(
            hospital=cls.hospital_alpha,
            name="Cardiology",
            code="CARD-01",
            department_type=DepartmentType.CLINICAL,
        )
        cls.dept_beta_general = Department.objects.create(
            hospital=cls.hospital_beta,
            name="General Medicine",
            code="GEN-01",
            department_type=DepartmentType.CLINICAL,
        )

        # 3. Hospital Admin for Hospital Alpha
        cls.admin_alpha_user = User.objects.create_user(
            email="admin.alpha@hospital.com",
            phone="+8801700000001",
            password="AdminAlphaPass123!",
            first_name="Alpha",
            last_name="Administrator",
        )
        cls.admin_alpha_emp = Employee.objects.create(
            user=cls.admin_alpha_user,
            hospital=cls.hospital_alpha,
            department=cls.dept_cardio,
            employee_id="ADM-ALP-001",
            designation="Chief Administrator",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 4. Doctor User
        cls.doctor_user = User.objects.create_user(
            email="doctor.tariq@hospital.com",
            phone="+8801700000002",
            password="DoctorPass123!",
            first_name="Tariq",
            last_name="Ahmed",
        )

        # 5. Non-admin Staff User
        cls.staff_user = User.objects.create_user(
            email="staff.reception@hospital.com",
            phone="+8801700000003",
            password="StaffPass123!",
            first_name="Reception",
            last_name="Staff",
        )
        cls.staff_emp = Employee.objects.create(
            user=cls.staff_user,
            hospital=cls.hospital_alpha,
            department=cls.dept_cardio,
            employee_id="REC-ALP-001",
            designation="Front Desk",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 6. Inactive User
        cls.inactive_user = User.objects.create_user(
            email="inactive@hospital.com",
            password="InactivePass123!",
            is_active=False,
        )

    # ==========================================================================
    # AUTHENTICATION TESTS (Phase 1C)
    # ==========================================================================

    def test_email_login_success(self):
        """User can authenticate successfully using normalized email."""
        url = reverse("auth-login")
        response = self.client.post(
            url,
            {"username": "DOCTOR.TARIQ@HOSPITAL.COM", "password": "DoctorPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "doctor.tariq@hospital.com")

    def test_phone_login_success(self):
        """User can authenticate successfully using phone number."""
        url = reverse("auth-login")
        response = self.client.post(
            url,
            {"username": "+8801700000002", "password": "DoctorPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["phone"], "+8801700000002")

    def test_invalid_credentials_rejected(self):
        """Invalid passwords or non-existent usernames must return 400 Bad Request."""
        url = reverse("auth-login")
        response = self.client.post(
            url,
            {"username": "doctor.tariq@hospital.com", "password": "WrongPassword!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_user_login_rejected(self):
        """Inactive accounts must be blocked from logging in."""
        url = reverse("auth-login")
        response = self.client.post(
            url,
            {"username": "inactive@hospital.com", "password": "InactivePass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("inactive", str(response.data))

    def test_authenticated_profile_endpoint(self):
        """GET /api/core/auth/me/ returns authenticated profile details."""
        self.client.force_authenticate(user=self.admin_alpha_user)
        url = reverse("auth-me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], str(self.admin_alpha_user.id))
        self.assertEqual(len(response.data["employments"]), 1)
        self.assertEqual(response.data["employments"][0]["role"], EmployeeRole.HOSPITAL_ADMIN)

    def test_password_change_success(self):
        """Authenticated user can change their password with valid current password."""
        self.client.force_authenticate(user=self.doctor_user)
        url = reverse("auth-password-change")
        response = self.client.post(
            url,
            {"old_password": "DoctorPass123!", "new_password": "NewSecretPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doctor_user.refresh_from_db()
        self.assertTrue(self.doctor_user.check_password("NewSecretPass456!"))

    def test_logout_clears_session(self):
        """POST /api/core/auth/logout/ flushes the session."""
        self.client.force_authenticate(user=self.doctor_user)
        url = reverse("auth-logout")
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ==========================================================================
    # EMPLOYEE MANAGEMENT TESTS (Phase 1D)
    # ==========================================================================

    def test_employee_registration_workflow(self):
        """User can submit an application which starts in PENDING status."""
        self.client.force_authenticate(user=self.doctor_user)
        url = reverse("employee-register")
        payload = {
            "hospital": str(self.hospital_alpha.id),
            "department": str(self.dept_cardio.id),
            "employee_id": "DOC-ALP-101",
            "designation": "Associate Cardiologist",
            "role": EmployeeRole.DOCTOR,
            "joining_date": str(datetime.date.today()),
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["employee"]["approval_status"], ApprovalStatus.PENDING)
        self.assertIsNone(response.data["employee"]["approved_by"])

    def test_hospital_admin_can_approve_employee(self):
        """Authorized Hospital Admin in same hospital can approve application."""
        # Create applicant in hospital_alpha
        applicant_emp = Employee.objects.create(
            user=self.doctor_user,
            hospital=self.hospital_alpha,
            department=self.dept_cardio,
            employee_id="DOC-TO-APPROVE",
            designation="Fellow",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
        )

        self.client.force_authenticate(user=self.admin_alpha_user)
        url = reverse("employee-approve", args=[applicant_emp.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        applicant_emp.refresh_from_db()
        self.assertEqual(applicant_emp.approval_status, ApprovalStatus.APPROVED)
        self.assertEqual(applicant_emp.approved_by, self.admin_alpha_emp)
        self.assertIsNotNone(applicant_emp.approved_at)

    def test_self_approval_rejected(self):
        """An administrator cannot approve their own employee application."""
        self.client.force_authenticate(user=self.admin_alpha_user)
        url = reverse("employee-approve", args=[self.admin_alpha_emp.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot approve their own", str(response.data))

    def test_non_admin_approval_rejected(self):
        """A regular staff member (non-admin) cannot approve employees."""
        applicant_emp = Employee.objects.create(
            user=self.doctor_user,
            hospital=self.hospital_alpha,
            department=self.dept_cardio,
            employee_id="DOC-PENDING-02",
            designation="Fellow",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
        )

        self.client.force_authenticate(user=self.staff_user)  # Receptionist
        url = reverse("employee-approve", args=[applicant_emp.id])
        response = self.client.post(url, HTTP_X_HOSPITAL_ID=str(self.hospital_alpha.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_hospital_approval_rejected(self):
        """An admin from Hospital Alpha cannot approve an employee in Hospital Beta."""
        # Create employee applicant in Hospital Beta
        beta_applicant = Employee.objects.create(
            user=self.doctor_user,
            hospital=self.hospital_beta,
            department=self.dept_beta_general,
            employee_id="DOC-BETA-APP",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
        )

        # Admin Alpha attempts to approve Beta applicant
        self.client.force_authenticate(user=self.admin_alpha_user)
        url = reverse("employee-approve", args=[beta_applicant.id])
        response = self.client.post(url)
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_duplicate_employee_per_hospital_rejected_via_api(self):
        """Attempting to register twice in the same hospital returns 400 Bad Request."""
        # Staff user already has employment in hospital_alpha
        self.client.force_authenticate(user=self.staff_user)
        url = reverse("employee-register")
        payload = {
            "hospital": str(self.hospital_alpha.id),
            "department": str(self.dept_cardio.id),
            "employee_id": "REC-ALP-DUPL",
            "designation": "Assistant",
            "role": EmployeeRole.RECEPTIONIST,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already have an employment record", str(response.data))

    def test_multi_hospital_employment_allowed_via_api(self):
        """Staff user can apply for a position in Hospital Beta while employed at Alpha."""
        self.client.force_authenticate(user=self.staff_user)
        url = reverse("employee-register")
        payload = {
            "hospital": str(self.hospital_beta.id),
            "department": str(self.dept_beta_general.id),
            "employee_id": "STAFF-BETA-01",
            "designation": "Evening Consultant",
            "role": EmployeeRole.GENERAL_STAFF,
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.staff_user.employee_profiles.count(), 2)

    def test_hospital_admin_can_reject_employee(self):
        """Hospital Admin can reject an employee application."""
        applicant_emp = Employee.objects.create(
            user=self.doctor_user,
            hospital=self.hospital_alpha,
            department=self.dept_cardio,
            employee_id="DOC-TO-REJECT",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
        )

        self.client.force_authenticate(user=self.admin_alpha_user)
        url = reverse("employee-reject", args=[applicant_emp.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        applicant_emp.refresh_from_db()
        self.assertEqual(applicant_emp.approval_status, ApprovalStatus.REJECTED)

    def test_employee_status_update_by_admin(self):
        """Hospital Admin can update employee designation or employment status."""
        self.client.force_authenticate(user=self.admin_alpha_user)
        url = reverse("employee-update-status", args=[self.staff_emp.id])
        response = self.client.patch(
            url,
            {"designation": "Lead Front Desk Officer", "employment_status": EmploymentStatus.ON_LEAVE},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.staff_emp.refresh_from_db()
        self.assertEqual(self.staff_emp.designation, "Lead Front Desk Officer")
        self.assertEqual(self.staff_emp.employment_status, EmploymentStatus.ON_LEAVE)
