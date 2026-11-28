import json
import datetime
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.contrib.admin.views.autocomplete import AutocompleteJsonView

from apps.hospitals.models import Hospital
from apps.core.models import (
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)
from apps.doctors.models import Doctor, DoctorDepartment
from apps.patients.models import Patient, PatientVisit
from apps.hospitals.admin import HospitalAdmin
from apps.doctors.admin import DoctorAdmin
from apps.patients.admin import PatientAdmin, PatientVisitAdmin
from apps.clinic.models import Appointment
from apps.clinic.admin import AppointmentAdmin

User = get_user_model()


class DummyAdminSite(AdminSite):
    pass


class AdminTenantSecurityAndAutocompleteTests(TestCase):
    """
    Focused security tests for SEC-01 and SEC-03:
    1. Superuser global access on Doctor, Patient, Hospital, and PatientVisit.
    2. Hospital A employee cannot access Hospital B doctors in admin queryset.
    3. Hospital A employee cannot access Hospital B patients in admin queryset.
    4. Hospital A employee cannot access Hospital B patient visits in admin queryset.
    5. Pending/rejected employee gets no unauthorized results.
    6. Suspended/resigned employee gets no unauthorized results.
    7. User without membership gets no records.
    8. Multi-hospital employee sees only records from their approved active memberships.
    9. Autocomplete endpoint does not leak foreign-hospital patient data.
    10. Autocomplete endpoint does not leak foreign-hospital doctor data.
    11. Hospital autocomplete does not expose unauthorized hospitals.
    12. Object-level view/change/delete permission check denies foreign hospital records.
    """

    @classmethod
    def setUpTestData(cls):
        # 1. Hospitals
        cls.hospital_a = Hospital.objects.create(
            name="Alpha General Hospital",
            registration_number="HOSP-ALPHA-SEC",
            phone="01710000001",
        )
        cls.hospital_b = Hospital.objects.create(
            name="Beta Specialized Hospital",
            registration_number="HOSP-BETA-SEC",
            phone="01720000002",
        )
        cls.hospital_c = Hospital.objects.create(
            name="Gamma Clinic",
            registration_number="HOSP-GAMMA-SEC",
            phone="01730000003",
        )

        # 2. Users
        cls.superuser = User.objects.create_superuser(
            email="super@hms.com",
            password="SuperPassword123!",
        )

        # Staff in Hospital A
        cls.user_staff_a = User.objects.create_user(
            email="staff.a@hms.com",
            password="StaffPassword123!",
            is_staff=True,
            is_superuser=False,
        )
        # Grant model view/change/delete permissions so Django's permission checks pass
        from django.contrib.auth.models import Permission
        for codename in [
            "view_doctor", "change_doctor", "delete_doctor",
            "view_patient", "change_patient", "delete_patient",
            "view_patientvisit", "change_patientvisit", "delete_patientvisit",
            "view_hospital", "change_hospital", "delete_hospital",
            "view_appointment", "change_appointment", "delete_appointment",
        ]:
            perm = Permission.objects.filter(codename=codename).first()
            if perm:
                cls.user_staff_a.user_permissions.add(perm)
        cls.emp_a = Employee.objects.create(
            user=cls.user_staff_a,
            hospital=cls.hospital_a,
            employee_id="EMP-A-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Staff in Hospital B
        cls.user_staff_b = User.objects.create_user(
            email="staff.b@hms.com",
            password="StaffPassword123!",
            is_staff=True,
        )
        cls.emp_b = Employee.objects.create(
            user=cls.user_staff_b,
            hospital=cls.hospital_b,
            employee_id="EMP-B-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Multi-hospital staff (A and B, but NOT C)
        cls.user_multi = User.objects.create_user(
            email="staff.multi@hms.com",
            password="StaffPassword123!",
            is_staff=True,
        )
        Employee.objects.create(
            user=cls.user_multi,
            hospital=cls.hospital_a,
            employee_id="EMP-MULTI-A",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )
        Employee.objects.create(
            user=cls.user_multi,
            hospital=cls.hospital_b,
            employee_id="EMP-MULTI-B",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Pending employee in Hospital A
        cls.user_pending = User.objects.create_user(
            email="staff.pending@hms.com",
            password="StaffPassword123!",
            is_staff=True,
        )
        Employee.objects.create(
            user=cls.user_pending,
            hospital=cls.hospital_a,
            employee_id="EMP-PENDING-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.PENDING,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Suspended employee in Hospital A
        cls.user_suspended = User.objects.create_user(
            email="staff.suspended@hms.com",
            password="StaffPassword123!",
            is_staff=True,
        )
        Employee.objects.create(
            user=cls.user_suspended,
            hospital=cls.hospital_a,
            employee_id="EMP-SUSPENDED-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.SUSPENDED,
        )

        # User with no employee record
        cls.user_no_membership = User.objects.create_user(
            email="staff.nomember@hms.com",
            password="StaffPassword123!",
            is_staff=True,
        )

        # 3. Medical Records
        # Doctors
        cls.dept_a = DoctorDepartment.objects.create(hospital=cls.hospital_a, name="Cardiology A")
        cls.dept_b = DoctorDepartment.objects.create(hospital=cls.hospital_b, name="Cardiology B")
        cls.dept_c = DoctorDepartment.objects.create(hospital=cls.hospital_c, name="Cardiology C")

        cls.doctor_a = Doctor.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept_a,
            doctor_code="DOC-A-01",
            first_name="DrAlpha",
            last_name="One",
            gender=Doctor.Gender.MALE,
            phone="01711111111",
            status=Doctor.Status.ACTIVE,
        )
        cls.doctor_b = Doctor.objects.create(
            hospital=cls.hospital_b,
            department=cls.dept_b,
            doctor_code="DOC-B-01",
            first_name="DrBeta",
            last_name="Two",
            gender=Doctor.Gender.MALE,
            phone="01722222222",
            status=Doctor.Status.ACTIVE,
        )
        cls.doctor_c = Doctor.objects.create(
            hospital=cls.hospital_c,
            department=cls.dept_c,
            doctor_code="DOC-C-01",
            first_name="DrGamma",
            last_name="Three",
            gender=Doctor.Gender.MALE,
            phone="01733333333",
            status=Doctor.Status.ACTIVE,
        )

        # Patients
        cls.patient_a = Patient.objects.create(
            hospital=cls.hospital_a,
            patient_number="PAT-A-001",
            first_name="JohnAlpha",
            last_name="Doe",
            gender="male",
            phone="01811111111",
        )
        cls.patient_b = Patient.objects.create(
            hospital=cls.hospital_b,
            patient_number="PAT-B-001",
            first_name="JaneBeta",
            last_name="Smith",
            gender="female",
            phone="01822222222",
        )
        cls.patient_c = Patient.objects.create(
            hospital=cls.hospital_c,
            patient_number="PAT-C-001",
            first_name="JimGamma",
            last_name="Brown",
            gender="male",
            phone="01833333333",
        )

        # Patient Visits
        cls.visit_a = PatientVisit.objects.create(
            hospital=cls.hospital_a,
            patient=cls.patient_a,
            visit_number="VIS-A-001",
            visit_type="opd",
            visit_date=datetime.date.today(),
        )
        cls.visit_b = PatientVisit.objects.create(
            hospital=cls.hospital_b,
            patient=cls.patient_b,
            visit_number="VIS-B-001",
            visit_type="opd",
            visit_date=datetime.date.today(),
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.site = DummyAdminSite()
        self.doctor_admin = DoctorAdmin(Doctor, self.site)
        self.patient_admin = PatientAdmin(Patient, self.site)
        self.patient_visit_admin = PatientVisitAdmin(PatientVisit, self.site)
        self.hospital_admin = HospitalAdmin(Hospital, self.site)
        self.appointment_admin = AppointmentAdmin(Appointment, self.site)

    # ==========================================================
    # 1. QUERYSET ISOLATION TESTS
    # ==========================================================

    def test_superuser_retains_global_access(self):
        """Superuser gets full access across all hospitals."""
        request = self.factory.get("/admin/")
        request.user = self.superuser

        self.assertEqual(self.doctor_admin.get_queryset(request).count(), 3)
        self.assertEqual(self.patient_admin.get_queryset(request).count(), 3)
        self.assertEqual(self.hospital_admin.get_queryset(request).count(), 3)
        self.assertEqual(self.patient_visit_admin.get_queryset(request).count(), 2)

    def test_hospital_a_employee_cannot_see_hospital_b_doctors(self):
        """Staff from Hospital A only sees Doctor A, never Doctor B or C."""
        request = self.factory.get("/admin/")
        request.user = self.user_staff_a

        qs = self.doctor_admin.get_queryset(request)
        self.assertEqual(list(qs), [self.doctor_a])
        self.assertNotIn(self.doctor_b, qs)
        self.assertNotIn(self.doctor_c, qs)

    def test_hospital_a_employee_cannot_see_hospital_b_patients(self):
        """Staff from Hospital A only sees Patient A, never Patient B or C."""
        request = self.factory.get("/admin/")
        request.user = self.user_staff_a

        qs = self.patient_admin.get_queryset(request)
        self.assertEqual(list(qs), [self.patient_a])
        self.assertNotIn(self.patient_b, qs)
        self.assertNotIn(self.patient_c, qs)

    def test_hospital_a_employee_cannot_see_hospital_b_visits(self):
        """Staff from Hospital A only sees Visit A, never Visit B."""
        request = self.factory.get("/admin/")
        request.user = self.user_staff_a

        qs = self.patient_visit_admin.get_queryset(request)
        self.assertEqual(list(qs), [self.visit_a])
        self.assertNotIn(self.visit_b, qs)

    def test_pending_employee_sees_empty_queryset(self):
        """Pending approval employee receives an empty queryset."""
        request = self.factory.get("/admin/")
        request.user = self.user_pending

        self.assertEqual(self.doctor_admin.get_queryset(request).count(), 0)
        self.assertEqual(self.patient_admin.get_queryset(request).count(), 0)
        self.assertEqual(self.hospital_admin.get_queryset(request).count(), 0)

    def test_suspended_employee_sees_empty_queryset(self):
        """Suspended employee receives an empty queryset."""
        request = self.factory.get("/admin/")
        request.user = self.user_suspended

        self.assertEqual(self.doctor_admin.get_queryset(request).count(), 0)
        self.assertEqual(self.patient_admin.get_queryset(request).count(), 0)
        self.assertEqual(self.hospital_admin.get_queryset(request).count(), 0)

    def test_user_without_membership_sees_empty_queryset(self):
        """Staff user without an employee record receives an empty queryset."""
        request = self.factory.get("/admin/")
        request.user = self.user_no_membership

        self.assertEqual(self.doctor_admin.get_queryset(request).count(), 0)
        self.assertEqual(self.patient_admin.get_queryset(request).count(), 0)
        self.assertEqual(self.hospital_admin.get_queryset(request).count(), 0)

    def test_multi_hospital_employee_sees_only_approved_memberships(self):
        """User with approved memberships in A and B sees records from A and B, but NOT C."""
        request = self.factory.get("/admin/")
        request.user = self.user_multi

        doc_qs = self.doctor_admin.get_queryset(request)
        self.assertIn(self.doctor_a, doc_qs)
        self.assertIn(self.doctor_b, doc_qs)
        self.assertNotIn(self.doctor_c, doc_qs)

        pat_qs = self.patient_admin.get_queryset(request)
        self.assertIn(self.patient_a, pat_qs)
        self.assertIn(self.patient_b, pat_qs)
        self.assertNotIn(self.patient_c, pat_qs)

        hosp_qs = self.hospital_admin.get_queryset(request)
        self.assertIn(self.hospital_a, hosp_qs)
        self.assertIn(self.hospital_b, hosp_qs)
        self.assertNotIn(self.hospital_c, hosp_qs)

    # ==========================================================
    # 2. AUTOCOMPLETE ENDPOINT SECURITY TESTS
    # ==========================================================

    def test_autocomplete_endpoint_does_not_leak_other_hospital_patients(self):
        """
        The Django Admin autocomplete endpoint for Appointment.patient
        must NOT return patients from Hospital B when requested by Staff A.
        """
        from django.contrib.admin import site
        request = self.factory.get(
            "/admin/autocomplete/",
            {
                "app_label": "clinic",
                "model_name": "appointment",
                "field_name": "patient",
                "term": "JaneBeta",  # Searching for Hospital B's patient
            },
        )
        request.user = self.user_staff_a
        view = AutocompleteJsonView.as_view(admin_site=site)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Results must be empty because JaneBeta belongs to Hospital B
        self.assertEqual(len(data["results"]), 0)

        # Searching for Patient A must succeed
        request_a = self.factory.get(
            "/admin/autocomplete/",
            {
                "app_label": "clinic",
                "model_name": "appointment",
                "field_name": "patient",
                "term": "JohnAlpha",
            },
        )
        request_a.user = self.user_staff_a
        response_a = view(request_a)
        data_a = json.loads(response_a.content)
        self.assertEqual(len(data_a["results"]), 1)
        self.assertEqual(data_a["results"][0]["id"], str(self.patient_a.id))

    def test_autocomplete_endpoint_does_not_leak_other_hospital_doctors(self):
        """
        The Django Admin autocomplete endpoint for Appointment.doctor
        must NOT return doctors from Hospital B when requested by Staff A.
        """
        from django.contrib.admin import site
        request = self.factory.get(
            "/admin/autocomplete/",
            {
                "app_label": "clinic",
                "model_name": "appointment",
                "field_name": "doctor",
                "term": "DrBeta",
            },
        )
        request.user = self.user_staff_a
        view = AutocompleteJsonView.as_view(admin_site=site)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["results"]), 0)

    def test_autocomplete_endpoint_does_not_leak_other_hospitals(self):
        """
        The Django Admin autocomplete endpoint for Appointment.hospital
        must only return Hospital A for Staff A, never Hospital B or C.
        """
        from django.contrib.admin import site
        request = self.factory.get(
            "/admin/autocomplete/",
            {
                "app_label": "clinic",
                "model_name": "appointment",
                "field_name": "hospital",
                "term": "Beta",
            },
        )
        request.user = self.user_staff_a
        view = AutocompleteJsonView.as_view(admin_site=site)
        response = view(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["results"]), 0)

    # ==========================================================
    # 3. OBJECT-LEVEL PERMISSION ENFORCEMENT
    # ==========================================================

    def test_object_level_permissions_deny_foreign_hospital_records(self):
        """
        has_view_permission, has_change_permission, and has_delete_permission
        must reject objects from other hospitals.
        """
        request = self.factory.get("/admin/")
        request.user = self.user_staff_a

        # Hospital A records: permitted
        self.assertTrue(self.patient_admin.has_view_permission(request, self.patient_a))
        self.assertTrue(self.patient_admin.has_change_permission(request, self.patient_a))
        self.assertTrue(self.patient_admin.has_delete_permission(request, self.patient_a))

        # Hospital B records: denied
        self.assertFalse(self.patient_admin.has_view_permission(request, self.patient_b))
        self.assertFalse(self.patient_admin.has_change_permission(request, self.patient_b))
        self.assertFalse(self.patient_admin.has_delete_permission(request, self.patient_b))
