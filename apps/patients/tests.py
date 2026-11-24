import datetime
import uuid
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.hospitals.models import Hospital
from apps.patients.models import Patient, PatientVisit
from apps.core.models import (
    Employee,
    EmployeeRole,
    ApprovalStatus,
    EmploymentStatus,
)

User = get_user_model()


class PatientSecurityAndRBACTests(APITestCase):
    """
    Security and RBAC test suite for Patient and PatientVisit endpoints:
    1. Anonymous access rejected (401).
    2. Unapproved employee rejected (403).
    3. Inactive employee rejected (403).
    4. Cross-hospital patient isolation (Hospital A cannot view, update, delete Hospital B patients).
    5. Cross-hospital patient visit isolation.
    6. Role-based permissions (Admin, Doctor, Nurse, Receptionist, Accountant/Lab Tech).
    7. Patient registration cannot assign unauthorized hospital.
    8. Cross-hospital patient-visit creation rejection (patient belonging to Hospital B cannot be assigned to Hospital A visit).
    9. Delete operations restricted strictly to Hospital Admin.
    10. Existing functionality (validation, update, delete with visits).
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Setup two distinct hospital tenants
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-A-SEC",
            name="Hospital Alpha",
            address="Dhaka, Bangladesh",
            phone="01710000001",
            email="info@alpha.org",
        )
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-B-SEC",
            name="Hospital Beta",
            address="Sylhet, Bangladesh",
            phone="01720000002",
            email="info@beta.org",
        )

        # 2. Staff in Hospital A:
        # 2.1 Hospital Admin
        cls.admin_a_user = User.objects.create_user(
            email="admin.a@alpha.org",
            phone="+8801710000001",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="Alpha",
        )
        cls.admin_a_emp = Employee.objects.create(
            user=cls.admin_a_user,
            hospital=cls.hospital_a,
            employee_id="ADM-A-01",
            designation="Administrator",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 2.2 Doctor
        cls.doctor_a_user = User.objects.create_user(
            email="doctor.a@alpha.org",
            phone="+8801710000002",
            password="DoctorPassword123!",
            first_name="Doctor",
            last_name="Alpha",
        )
        cls.doctor_a_emp = Employee.objects.create(
            user=cls.doctor_a_user,
            hospital=cls.hospital_a,
            employee_id="DOC-A-01",
            designation="Physician",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 2.3 Nurse
        cls.nurse_a_user = User.objects.create_user(
            email="nurse.a@alpha.org",
            phone="+8801710000003",
            password="NursePassword123!",
            first_name="Nurse",
            last_name="Alpha",
        )
        cls.nurse_a_emp = Employee.objects.create(
            user=cls.nurse_a_user,
            hospital=cls.hospital_a,
            employee_id="NUR-A-01",
            designation="Head Nurse",
            role=EmployeeRole.NURSE,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 2.4 Receptionist
        cls.receptionist_a_user = User.objects.create_user(
            email="reception.a@alpha.org",
            phone="+8801710000004",
            password="ReceptionPassword123!",
            first_name="Reception",
            last_name="Alpha",
        )
        cls.receptionist_a_emp = Employee.objects.create(
            user=cls.receptionist_a_user,
            hospital=cls.hospital_a,
            employee_id="REC-A-01",
            designation="Front Desk",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 2.5 Accountant (Unauthorized for direct clinical patient management)
        cls.accountant_a_user = User.objects.create_user(
            email="accountant.a@alpha.org",
            phone="+8801710000005",
            password="AccountantPassword123!",
            first_name="Accountant",
            last_name="Alpha",
        )
        cls.accountant_a_emp = Employee.objects.create(
            user=cls.accountant_a_user,
            hospital=cls.hospital_a,
            employee_id="ACC-A-01",
            designation="Accounts Officer",
            role=EmployeeRole.ACCOUNTANT,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 2.6 Unapproved Staff
        cls.unapproved_user = User.objects.create_user(
            email="unapproved@alpha.org",
            phone="+8801710000006",
            password="UnapprovedPass123!",
        )
        cls.unapproved_emp = Employee.objects.create(
            user=cls.unapproved_user,
            hospital=cls.hospital_a,
            employee_id="PEN-A-01",
            designation="Intern",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 2.7 Inactive/Suspended Staff
        cls.suspended_user = User.objects.create_user(
            email="suspended@alpha.org",
            phone="+8801710000007",
            password="SuspendedPass123!",
        )
        cls.suspended_emp = Employee.objects.create(
            user=cls.suspended_user,
            hospital=cls.hospital_a,
            employee_id="SUS-A-01",
            designation="Former Nurse",
            role=EmployeeRole.NURSE,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.SUSPENDED,
        )

        # 3. Staff in Hospital B:
        cls.admin_b_user = User.objects.create_user(
            email="admin.b@beta.org",
            phone="+8801720000001",
            password="AdminBPassword123!",
            first_name="Admin",
            last_name="Beta",
        )
        cls.admin_b_emp = Employee.objects.create(
            user=cls.admin_b_user,
            hospital=cls.hospital_b,
            employee_id="ADM-B-01",
            designation="Administrator",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # 4. Seed Patients:
        # Patient in Hospital A
        cls.patient_a = Patient.objects.create(
            hospital=cls.hospital_a,
            patient_number="PAT-A-001",
            first_name="Alice",
            last_name="Alpha",
            date_of_birth="1990-01-01",
            gender="female",
            phone="01711111111",
            status="active",
        )
        # Patient in Hospital B
        cls.patient_b = Patient.objects.create(
            hospital=cls.hospital_b,
            patient_number="PAT-B-001",
            first_name="Bob",
            last_name="Beta",
            date_of_birth="1992-02-02",
            gender="male",
            phone="01722222222",
            status="active",
        )

        # 5. Seed Patient Visits:
        cls.visit_a = PatientVisit.objects.create(
            hospital=cls.hospital_a,
            patient=cls.patient_a,
            visit_number="VIS-A-001",
            visit_type="opd",
            visit_date=timezone.now(),
            chief_complaint="Fever",
            status="registered",
        )
        cls.visit_b = PatientVisit.objects.create(
            hospital=cls.hospital_b,
            patient=cls.patient_b,
            visit_number="VIS-B-001",
            visit_type="opd",
            visit_date=timezone.now(),
            chief_complaint="Headache",
            status="registered",
        )

    # --------------------------------------------------------------------------
    # 1. AUTHENTICATION & MEMBERSHIP CHECKS
    # --------------------------------------------------------------------------

    def test_anonymous_requests_rejected(self):
        """Unauthenticated requests must be rejected (401 or 403)."""
        list_url = reverse("patient-list")
        res = self.client.get(list_url)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        detail_url = reverse("patient-detail", args=[self.patient_a.id])
        res = self.client.get(detail_url)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        visit_list_url = reverse("patient-visit-list")
        res = self.client.get(visit_list_url)
        self.assertIn(res.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_unapproved_employee_rejected(self):
        """User with pending approval cannot access patient endpoints."""
        self.client.force_authenticate(user=self.unapproved_user)
        res = self.client.get(
            reverse("patient-list"),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_employee_rejected(self):
        """Suspended employee cannot access patient endpoints."""
        self.client.force_authenticate(user=self.suspended_user)
        res = self.client.get(
            reverse("patient-list"),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_role_rejected(self):
        """Accountant role is not in PATIENT_READ_ROLES and cannot access clinical patient lists."""
        self.client.force_authenticate(user=self.accountant_a_user)
        res = self.client.get(
            reverse("patient-list"),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # --------------------------------------------------------------------------
    # 2. CROSS-HOSPITAL TENANT ISOLATION
    # --------------------------------------------------------------------------

    def test_hospital_isolation_patient_list(self):
        """Staff in Hospital A only sees Hospital A patients."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.get(
            reverse("patient-list"),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        patient_ids = [p["id"] for p in res.data]
        self.assertIn(str(self.patient_a.id), patient_ids)
        self.assertNotIn(str(self.patient_b.id), patient_ids)

    def test_hospital_isolation_patient_retrieve(self):
        """Staff in Hospital A cannot retrieve Hospital B patient by ID (404 Not Found)."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.get(
            reverse("patient-detail", args=[self.patient_b.id]),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_hospital_update_blocked(self):
        """Staff in Hospital A cannot update a Hospital B patient."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.patch(
            reverse("patient-detail", args=[self.patient_b.id]),
            {"first_name": "Tampered"},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.patient_b.refresh_from_db()
        self.assertEqual(self.patient_b.first_name, "Bob")

    def test_cross_hospital_visit_isolation(self):
        """Staff in Hospital A cannot view Hospital B visits."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.get(
            reverse("patient-visit-list"),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        visit_ids = [v["id"] for v in res.data]
        self.assertIn(str(self.visit_a.id), visit_ids)
        self.assertNotIn(str(self.visit_b.id), visit_ids)

        # Direct detail access
        detail_res = self.client.get(
            reverse("patient-visit-detail", args=[self.visit_b.id]),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(detail_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_spoofed_hospital_header_rejected(self):
        """User from Hospital A cannot pass Hospital B in X-Hospital-ID header."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.get(
            reverse("patient-list"),
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.id),  # Spoofed
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # --------------------------------------------------------------------------
    # 3. RBAC & PERMISSION SPECIFIC TESTS
    # --------------------------------------------------------------------------

    def test_doctor_can_create_and_update_patient(self):
        """Doctor has full create and update rights for patients in their hospital."""
        self.client.force_authenticate(user=self.doctor_a_user)
        url = reverse("patient-list")
        data = {
            "hospital": str(self.hospital_a.id),
            "patient_number": "PAT-DOC-001",
            "first_name": "Charlie",
            "last_name": "Brown",
            "gender": "male",
            "phone": "01733333333",
            "status": "active",
        }
        res = self.client.post(url, data, format="json", HTTP_X_HOSPITAL_ID=str(self.hospital_a.id))
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created_id = res.data["id"]
        # Update
        patch_res = self.client.patch(
            reverse("patient-detail", args=[created_id]),
            {"last_name": "Updated"},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["last_name"], "Updated")

    def test_nurse_and_receptionist_can_create_patient(self):
        """Nurse and Receptionist can register new patients."""
        for u in [self.nurse_a_user, self.receptionist_a_user]:
            self.client.force_authenticate(user=u)
            p_num = f"PAT-{u.id.hex[:6]}"
            res = self.client.post(
                reverse("patient-list"),
                {
                    "hospital": str(self.hospital_a.id),
                    "patient_number": p_num,
                    "first_name": "Test",
                    "gender": "female",
                    "phone": "01744444444",
                    "status": "active",
                },
                format="json",
                HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_non_admin_cannot_delete_patient(self):
        """Doctors, nurses, and receptionists cannot DELETE patients (strictly Admin)."""
        temp_patient = Patient.objects.create(
            hospital=self.hospital_a,
            patient_number="PAT-DEL-TEMP",
            first_name="Temp",
            gender="male",
            phone="01755555555",
            status="active",
        )
        for u in [self.doctor_a_user, self.nurse_a_user, self.receptionist_a_user]:
            self.client.force_authenticate(user=u)
            res = self.client.delete(
                reverse("patient-detail", args=[temp_patient.id]),
                HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
            )
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Hospital Admin can delete patient
        self.client.force_authenticate(user=self.admin_a_user)
        admin_del_res = self.client.delete(
            reverse("patient-detail", args=[temp_patient.id]),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(admin_del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Patient.objects.filter(id=temp_patient.id).exists())

    def test_patient_cannot_be_deleted_with_visits(self):
        """Even Hospital Admin cannot delete patient if visit records exist."""
        self.client.force_authenticate(user=self.admin_a_user)
        res = self.client.delete(
            reverse("patient-detail", args=[self.patient_a.id]),
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("visit records exist", str(res.data))
        self.assertTrue(Patient.objects.filter(id=self.patient_a.id).exists())

    def test_patient_registration_cannot_assign_unauthorized_hospital(self):
        """Staff from Hospital A cannot create a patient assigned to Hospital B."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(
            reverse("patient-list"),
            {
                "hospital": str(self.hospital_b.id),  # Hospital B!
                "patient_number": "PAT-ILLEGAL-01",
                "first_name": "Illegal",
                "gender": "male",
                "phone": "01766666666",
                "status": "active",
            },
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Patient.objects.filter(patient_number="PAT-ILLEGAL-01").exists())

    def test_visit_rejects_patient_from_another_hospital(self):
        """PatientVisit cannot link a patient from another hospital."""
        self.client.force_authenticate(user=self.doctor_a_user)
        res = self.client.post(
            reverse("patient-visit-list"),
            {
                "hospital": str(self.hospital_a.id),
                "patient": str(self.patient_b.id),  # Patient belongs to Hospital B!
                "visit_number": "VIS-INVALID-001",
                "visit_type": "opd",
                "visit_date": timezone.now().isoformat(),
                "status": "registered",
            },
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("patient", res.data)
