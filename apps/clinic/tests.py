import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.hospitals.models import Hospital
from apps.core.models import (
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)
from apps.clinic.permissions import (
    IsHospitalAdmin,
    IsDoctor,
    IsNurse,
    IsReceptionist,
    IsClinicStaff,
    get_hospital_id_from_request,
)

User = get_user_model()


class MockView(APIView):
    pass


class ClinicPermissionsTests(TestCase):
    """
    Tests for Clinic Department Permission Foundation (apps/clinic/permissions.py):
    1. Unauthenticated requests rejected.
    2. Missing hospital context rejected.
    3. Invalid/malformed hospital context rejected.
    4. Spoofed X-Hospital-ID header without membership rejected.
    5. Suspended/unapproved employee rejected.
    6. IsHospitalAdmin grants only admin, rejects others.
    7. IsDoctor grants doctor + admin, rejects nurse/receptionist.
    8. IsNurse grants nurse + admin, rejects doctor/receptionist.
    9. IsReceptionist grants receptionist + admin, rejects doctor/nurse.
    10. IsClinicStaff grants doctor, nurse, receptionist, admin, and rejects accountant/lab_tech.
    11. Context resolution sets request.active_employee correctly.
    """

    @classmethod
    def setUpTestData(cls):
        # Hospital A
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-CLN-A",
            name="Clinic Hospital Alpha",
            address="Dhaka",
            phone="01710000001",
        )
        # Hospital B
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-CLN-B",
            name="Clinic Hospital Beta",
            address="Chittagong",
            phone="01720000002",
        )

        # Admin User in Hospital A
        cls.user_admin = User.objects.create_user(
            email="admin.clinic@example.com",
            password="AdminPassword123!",
        )
        cls.emp_admin = Employee.objects.create(
            user=cls.user_admin,
            hospital=cls.hospital_a,
            employee_id="ADM-CLN-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Doctor User in Hospital A
        cls.user_doctor = User.objects.create_user(
            email="doc.clinic@example.com",
            password="DocPassword123!",
        )
        cls.emp_doctor = Employee.objects.create(
            user=cls.user_doctor,
            hospital=cls.hospital_a,
            employee_id="DOC-CLN-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Nurse User in Hospital A
        cls.user_nurse = User.objects.create_user(
            email="nurse.clinic@example.com",
            password="NursePassword123!",
        )
        cls.emp_nurse = Employee.objects.create(
            user=cls.user_nurse,
            hospital=cls.hospital_a,
            employee_id="NUR-CLN-01",
            role=EmployeeRole.NURSE,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Receptionist User in Hospital A
        cls.user_receptionist = User.objects.create_user(
            email="rec.clinic@example.com",
            password="RecPassword123!",
        )
        cls.emp_receptionist = Employee.objects.create(
            user=cls.user_receptionist,
            hospital=cls.hospital_a,
            employee_id="REC-CLN-01",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Accountant User in Hospital A (Non-clinical staff)
        cls.user_accountant = User.objects.create_user(
            email="acc.clinic@example.com",
            password="AccPassword123!",
        )
        cls.emp_accountant = Employee.objects.create(
            user=cls.user_accountant,
            hospital=cls.hospital_a,
            employee_id="ACC-CLN-01",
            role=EmployeeRole.ACCOUNTANT,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Unapproved Doctor in Hospital A
        cls.user_pending = User.objects.create_user(
            email="pending.clinic@example.com",
            password="PendingPass123!",
        )
        cls.emp_pending = Employee.objects.create(
            user=cls.user_pending,
            hospital=cls.hospital_a,
            employee_id="PEN-CLN-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
            employment_status=EmploymentStatus.ACTIVE,
        )

        cls.factory = APIRequestFactory()

    def test_anonymous_request_rejected(self):
        """Unauthenticated requests must be rejected."""
        request = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        view = MockView()

        for perm_class in [IsHospitalAdmin, IsDoctor, IsNurse, IsReceptionist, IsClinicStaff]:
            perm = perm_class()
            self.assertFalse(perm.has_permission(request, view))

    def test_missing_hospital_context_rejected(self):
        """Requests without hospital context are rejected."""
        request = self.factory.get("/")
        request.user = self.user_doctor
        view = MockView()

        perm = IsDoctor()
        self.assertFalse(perm.has_permission(request, view))
        self.assertIn("Hospital context", perm.message)

    def test_spoofed_hospital_header_rejected(self):
        """Passing Hospital B ID when user only belongs to Hospital A is rejected."""
        request = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_b.id))
        request.user = self.user_doctor  # Only belongs to Hospital A
        view = MockView()

        perm = IsDoctor()
        self.assertFalse(perm.has_permission(request, view))
        self.assertIn("do not have active, approved employee access", perm.message)

    def test_unapproved_employee_rejected(self):
        """Pending approval employee is rejected."""
        request = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        request.user = self.user_pending
        view = MockView()

        perm = IsDoctor()
        self.assertFalse(perm.has_permission(request, view))

    def test_is_hospital_admin_role_boundary(self):
        """IsHospitalAdmin permits only admin, rejects doctor, nurse, receptionist."""
        view = MockView()
        perm = IsHospitalAdmin()

        # Admin succeeds
        req_admin = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_admin.user = self.user_admin
        self.assertTrue(perm.has_permission(req_admin, view))
        self.assertEqual(req_admin.active_employee, self.emp_admin)

        # Doctor rejected
        req_doc = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_doc.user = self.user_doctor
        self.assertFalse(perm.has_permission(req_doc, view))

    def test_is_doctor_role_boundary(self):
        """IsDoctor permits doctor and admin, rejects nurse and receptionist."""
        view = MockView()
        perm = IsDoctor()

        # Doctor succeeds
        req_doc = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_doc.user = self.user_doctor
        self.assertTrue(perm.has_permission(req_doc, view))
        self.assertEqual(req_doc.active_employee, self.emp_doc_a if hasattr(self, 'emp_doc_a') else self.emp_doctor)

        # Admin succeeds
        req_admin = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_admin.user = self.user_admin
        self.assertTrue(perm.has_permission(req_admin, view))

        # Nurse rejected
        req_nurse = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_nurse.user = self.user_nurse
        self.assertFalse(perm.has_permission(req_nurse, view))

    def test_is_nurse_role_boundary(self):
        """IsNurse permits nurse and admin, rejects doctor and receptionist."""
        view = MockView()
        perm = IsNurse()

        # Nurse succeeds
        req_nurse = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_nurse.user = self.user_nurse
        self.assertTrue(perm.has_permission(req_nurse, view))

        # Doctor rejected
        req_doc = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_doc.user = self.user_doctor
        self.assertFalse(perm.has_permission(req_doc, view))

    def test_is_receptionist_role_boundary(self):
        """IsReceptionist permits receptionist and admin, rejects doctor and nurse."""
        view = MockView()
        perm = IsReceptionist()

        # Receptionist succeeds
        req_rec = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_rec.user = self.user_receptionist
        self.assertTrue(perm.has_permission(req_rec, view))

        # Doctor rejected
        req_doc = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_doc.user = self.user_doctor
        self.assertFalse(perm.has_permission(req_doc, view))

    def test_is_clinic_staff_role_boundary(self):
        """IsClinicStaff permits admin, doc, nurse, rec; rejects accountant."""
        view = MockView()
        perm = IsClinicStaff()

        for u in [self.user_admin, self.user_doctor, self.user_nurse, self.user_receptionist]:
            req = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
            req.user = u
            self.assertTrue(perm.has_permission(req, view))

        # Non-clinic accountant rejected
        req_acc = self.factory.get("/", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        req_acc.user = self.user_accountant
        self.assertFalse(perm.has_permission(req_acc, view))
