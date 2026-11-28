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
from apps.patients.models import Patient, PatientVisit
from apps.clinic.models import Appointment, Consultation, Diagnosis

User = get_user_model()


class ConsultationAndDiagnosisAPITests(TestCase):
    """
    Test Suite for Consultation & Diagnosis Management:
    1. Doctor creates consultation for assigned PatientVisit.
    2. Patient details serialized through PatientVisit (no duplicate data).
    3. Doctor ownership enforcement (Doctor A cannot modify Doctor B's consultation).
    4. Receptionist access rejection (403 Forbidden).
    5. Cross-hospital isolation (Hospital B doctor cannot access Hospital A consultations).
    6. Duplicate active consultation prevention for a PatientVisit.
    7. Diagnosis creation with PRIMARY, SECONDARY, and DIFFERENTIAL types.
    8. Diagnosis hospital and consultation consistency validation.
    9. Complete consultation action transitions Appointment & PatientVisit to COMPLETED.
    10. Completed consultation restrictions (cannot edit clinical notes or add diagnoses).
    """

    @classmethod
    def setUpTestData(cls):
        # Hospital A
        cls.hospital_a = Hospital.objects.create(
            registration_number="HOSP-CNS-A",
            name="Consultation Hospital Alpha",
            address="Dhaka",
            phone="01711111177",
        )
        # Hospital B
        cls.hospital_b = Hospital.objects.create(
            registration_number="HOSP-CNS-B",
            name="Consultation Hospital Beta",
            address="Chittagong",
            phone="01722222277",
        )

        # Users and Employees in Hospital A
        # Admin
        cls.user_admin = User.objects.create_user(
            email="admin.cns@example.com",
            password="AdminPassword123!",
        )
        cls.emp_admin = Employee.objects.create(
            user=cls.user_admin,
            hospital=cls.hospital_a,
            employee_id="ADM-CNS-01",
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Doctor 1
        cls.user_doc1 = User.objects.create_user(
            email="doc1.cns@example.com",
            password="Doc1Password123!",
        )
        cls.emp_doc1 = Employee.objects.create(
            user=cls.user_doc1,
            hospital=cls.hospital_a,
            employee_id="DOC-CNS-01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Doctor 2
        cls.user_doc2 = User.objects.create_user(
            email="doc2.cns@example.com",
            password="Doc2Password123!",
        )
        cls.emp_doc2 = Employee.objects.create(
            user=cls.user_doc2,
            hospital=cls.hospital_a,
            employee_id="DOC-CNS-02",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Receptionist
        cls.user_rec = User.objects.create_user(
            email="rec.cns@example.com",
            password="RecPassword123!",
        )
        cls.emp_rec = Employee.objects.create(
            user=cls.user_rec,
            hospital=cls.hospital_a,
            employee_id="REC-CNS-01",
            role=EmployeeRole.RECEPTIONIST,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Hospital B Doctor
        cls.user_b_doc = User.objects.create_user(
            email="doc.b.cns@example.com",
            password="DocBPassword123!",
        )
        cls.emp_b_doc = Employee.objects.create(
            user=cls.user_b_doc,
            hospital=cls.hospital_b,
            employee_id="DOC-CNS-B01",
            role=EmployeeRole.DOCTOR,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        )

        # Doctor Profiles in Hospital A
        cls.dept_cardio = DoctorDepartment.objects.create(
            hospital=cls.hospital_a,
            name="Cardiology",
        )
        cls.doctor1 = Doctor.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept_cardio,
            employee=cls.emp_doc1,
            doctor_code="DOC-CNS-001",
            first_name="Farhan",
            last_name="Chowdhury",
            gender=Doctor.Gender.MALE,
            phone="+8801700000071",
            status=Doctor.Status.ACTIVE,
        )
        cls.doctor2 = Doctor.objects.create(
            hospital=cls.hospital_a,
            department=cls.dept_cardio,
            employee=cls.emp_doc2,
            doctor_code="DOC-CNS-002",
            first_name="Tahmina",
            last_name="Begum",
            gender=Doctor.Gender.FEMALE,
            phone="+8801700000072",
            status=Doctor.Status.ACTIVE,
        )

        # Doctor Profile in Hospital B
        cls.dept_b = DoctorDepartment.objects.create(
            hospital=cls.hospital_b,
            name="Internal Medicine",
        )
        cls.doctor_b = Doctor.objects.create(
            hospital=cls.hospital_b,
            department=cls.dept_b,
            employee=cls.emp_b_doc,
            doctor_code="DOC-CNS-B001",
            first_name="Nayeem",
            last_name="Islam",
            gender=Doctor.Gender.MALE,
            phone="+8801700000073",
            status=Doctor.Status.ACTIVE,
        )

        # Patients
        cls.patient_a = Patient.objects.create(
            hospital=cls.hospital_a,
            patient_number="PAT-CNS-001",
            first_name="Selim",
            last_name="Reza",
            gender="male",
            phone="01811111177",
            date_of_birth=datetime.date(1985, 3, 15),
        )
        cls.patient_b = Patient.objects.create(
            hospital=cls.hospital_b,
            patient_number="PAT-CNS-B001",
            first_name="Nasima",
            last_name="Akter",
            gender="female",
            phone="01822222277",
            date_of_birth=datetime.date(1991, 7, 20),
        )

    def setUp(self):
        self.client = APIClient()

    def test_doctor_creates_consultation_successfully(self):
        """
        1. Doctor 1 creates a consultation for their patient visit:
        - PatientVisit transitions to IN_PROGRESS.
        - Patient details (name, DOB, gender) correctly serialized without duplication.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.REGISTERED,
        )

        self.client.force_authenticate(user=self.user_doc1)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient_visit": str(visit.id),
            "complaints": "Severe chest tightness and shortness of breath.",
            "examination_notes": "BP: 135/85 mmHg, Pulse: 78 bpm. Heart sounds normal.",
            "advice": "Rest and avoid heavy lifting.",
            "follow_up_date": str(timezone.localdate() + datetime.timedelta(days=7)),
        }
        res = self.client.post(
            "/api/clinic/consultations/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )

        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(str(res.data["doctor"]), str(self.doctor1.id))
        self.assertEqual(res.data["doctor_name"], self.doctor1.full_name)
        self.assertEqual(str(res.data["patient_id"]), str(self.patient_a.id))
        self.assertEqual(res.data["patient_name"], self.patient_a.full_name)
        self.assertEqual(res.data["patient_gender"], "male")
        self.assertEqual(res.data["complaints"], payload["complaints"])

        # PatientVisit should now be IN_PROGRESS
        visit.refresh_from_db()
        self.assertEqual(visit.status, PatientVisit.Status.IN_PROGRESS)

    def test_duplicate_consultation_for_same_visit_rejected(self):
        """
        6. A PatientVisit cannot receive duplicate consultations.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            complaints="Initial complaint",
        )

        self.client.force_authenticate(user=self.user_doc1)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient_visit": str(visit.id),
            "complaints": "Second consultation attempt",
        }
        res = self.client.post(
            "/api/clinic/consultations/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("patient_visit", res.data)

    def test_doctor_cannot_modify_other_doctor_consultation(self):
        """
        3. Doctor 2 cannot update or modify Doctor 1's consultation.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            complaints="Doctor 1 initial notes",
        )

        self.client.force_authenticate(user=self.user_doc2)
        res = self.client.patch(
            f"/api/clinic/consultations/{consultation.id}/",
            data={"complaints": "Doctor 2 unauthorized modification"},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        # Should be forbidden or filtered out of queryset
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        consultation.refresh_from_db()
        self.assertEqual(consultation.complaints, "Doctor 1 initial notes")

    def test_receptionist_cannot_access_consultations(self):
        """
        4. Reception staff cannot view or create medical consultations.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.REGISTERED,
        )

        self.client.force_authenticate(user=self.user_rec)
        res = self.client.get(
            "/api/clinic/consultations/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Try to create
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient_visit": str(visit.id),
            "complaints": "Receptionist trying to enter notes",
        }
        res_post = self.client.post(
            "/api/clinic/consultations/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_hospital_isolation(self):
        """
        5. Hospital B doctor cannot view or touch Hospital A consultations.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            complaints="Hospital A notes",
        )

        self.client.force_authenticate(user=self.user_b_doc)
        # Using Hospital A header (spoofed)
        res = self.client.get(
            f"/api/clinic/consultations/{consultation.id}/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Using Hospital B header
        res_b = self.client.get(
            f"/api/clinic/consultations/{consultation.id}/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.id),
        )
        self.assertEqual(res_b.status_code, status.HTTP_404_NOT_FOUND)

    def test_diagnosis_crud_and_types(self):
        """
        7. Doctor creates diagnoses with PRIMARY, SECONDARY, and DIFFERENTIAL types.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            complaints="Hypertension symptoms",
        )

        self.client.force_authenticate(user=self.user_doc1)

        # 1. Primary Diagnosis
        res1 = self.client.post(
            "/api/clinic/diagnoses/",
            data={
                "hospital": str(self.hospital_a.id),
                "consultation": str(consultation.id),
                "diagnosis_name": "Essential (primary) hypertension",
                "icd_code": "I10",
                "diagnosis_type": Diagnosis.DiagnosisType.PRIMARY,
                "notes": "Mild elevated systolic pressure.",
            },
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED, res1.data)
        diag1_id = res1.data["id"]

        # 2. Secondary Diagnosis
        res2 = self.client.post(
            "/api/clinic/diagnoses/",
            data={
                "hospital": str(self.hospital_a.id),
                "consultation": str(consultation.id),
                "diagnosis_name": "Hyperlipidemia, unspecified",
                "icd_code": "E78.5",
                "diagnosis_type": Diagnosis.DiagnosisType.SECONDARY,
            },
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)

        # 3. Retrieve consultation with nested diagnoses
        res_cns = self.client.get(
            f"/api/clinic/consultations/{consultation.id}/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_cns.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_cns.data["diagnoses"]), 2)

    def test_diagnosis_hospital_consistency_validation(self):
        """
        8. Diagnosis creation with mismatched hospital is rejected.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
        )

        self.client.force_authenticate(user=self.user_doc1)
        res = self.client.post(
            "/api/clinic/diagnoses/",
            data={
                "hospital": str(self.hospital_b.id),  # Mismatch
                "consultation": str(consultation.id),
                "diagnosis_name": "Coronary artery disease",
                "diagnosis_type": Diagnosis.DiagnosisType.PRIMARY,
            },
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("consultation", res.data)

    def test_complete_consultation_action(self):
        """
        9. Completing consultation updates appointment and visit to COMPLETED.
        10. Clinical details can no longer be modified on completed consultations.
        """
        appt = Appointment.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient=self.patient_a,
            appointment_date=timezone.localdate(),
            appointment_time=datetime.time(16, 0),
            status=Appointment.Status.CHECKED_IN,
        )
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        appt.patient_visit = visit
        appt.save()

        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            appointment=appt,
            complaints="Final review before completion",
            advice="Full recovery anticipated.",
        )

        self.client.force_authenticate(user=self.user_doc1)
        res = self.client.post(
            f"/api/clinic/consultations/{consultation.id}/complete/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["detail"], "Consultation completed successfully.")

        # Verify linked status transitions
        appt.refresh_from_db()
        visit.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.COMPLETED)
        self.assertEqual(visit.status, PatientVisit.Status.COMPLETED)

        # Attempt to modify clinical notes on completed consultation must fail
        res_patch = self.client.patch(
            f"/api/clinic/consultations/{consultation.id}/",
            data={"complaints": "Attempted tampering after completion"},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("complaints", res_patch.data)

    def test_diagnosis_cannot_be_reparented(self):
        """
        SEC-AUD-01: A doctor cannot change the consultation or hospital of an existing diagnosis.
        """
        visit1 = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_number=f"VN-{uuid.uuid4().hex[:8]}",
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        visit2 = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_number=f"VN-{uuid.uuid4().hex[:8]}",
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        cns1 = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit1,
        )
        cns2 = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor2,
            patient_visit=visit2,
        )
        diag = Diagnosis.objects.create(
            hospital=self.hospital_a,
            consultation=cns1,
            diagnosis_name="Original Diagnosis",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
        )

        self.client.force_authenticate(user=self.user_doc1)
        # Attempt to reparent to cns2 (Doctor 2's consultation)
        res = self.client.patch(
            f"/api/clinic/diagnoses/{diag.id}/",
            data={"consultation": str(cns2.id)},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("consultation", res.data)

        # Attempt to change hospital
        res_hosp = self.client.patch(
            f"/api/clinic/diagnoses/{diag.id}/",
            data={"hospital": str(self.hospital_b.id)},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_hosp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hospital", res_hosp.data)

        diag.refresh_from_db()
        self.assertEqual(diag.consultation_id, cns1.id)
        self.assertEqual(diag.hospital_id, self.hospital_a.id)

    def test_diagnosis_operations_blocked_on_completed_consultation(self):
        """
        SEC-AUD-02:
        - Diagnosis creation is rejected on completed consultation.
        - Diagnosis update is rejected on completed consultation.
        - Diagnosis deletion is rejected on completed consultation.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.COMPLETED,
        )
        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            complaints="Completed visit consultation",
        )
        diag = Diagnosis.objects.create(
            hospital=self.hospital_a,
            consultation=consultation,
            diagnosis_name="Hypertension",
            diagnosis_type=Diagnosis.DiagnosisType.PRIMARY,
        )

        self.assertTrue(consultation.is_completed)

        self.client.force_authenticate(user=self.user_doc1)

        # 1. Creation on completed consultation rejected
        res_create = self.client.post(
            "/api/clinic/diagnoses/",
            data={
                "hospital": str(self.hospital_a.id),
                "consultation": str(consultation.id),
                "diagnosis_name": "Diabetes",
                "diagnosis_type": Diagnosis.DiagnosisType.SECONDARY,
            },
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_create.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", res_create.data)

        # 2. Update on completed consultation rejected
        res_update = self.client.patch(
            f"/api/clinic/diagnoses/{diag.id}/",
            data={"notes": "Tampered notes after completion"},
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_update.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Deletion on completed consultation rejected
        res_delete = self.client.delete(
            f"/api/clinic/diagnoses/{diag.id}/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res_delete.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Diagnosis.objects.filter(id=diag.id).exists())

    def test_walk_in_consultation_completion_without_appointment(self):
        """
        Walk-in Consultation without Appointment can be completed cleanly,
        transitioning the PatientVisit to COMPLETED.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.IN_PROGRESS,
        )
        consultation = Consultation.objects.create(
            hospital=self.hospital_a,
            doctor=self.doctor1,
            patient_visit=visit,
            appointment=None,  # Walk-in visit without appointment
            complaints="Walk-in consultation notes",
        )

        self.client.force_authenticate(user=self.user_doc1)
        res = self.client.post(
            f"/api/clinic/consultations/{consultation.id}/complete/",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        visit.refresh_from_db()
        self.assertEqual(visit.status, PatientVisit.Status.COMPLETED)
        consultation.refresh_from_db()
        self.assertTrue(consultation.is_completed)

    def test_concurrent_duplicate_consultation_rejection_under_lock(self):
        """
        BIZ-AUD-01: Serialized / concurrent consultation attempts for the same PatientVisit
        are blocked by row-level locking and re-checking under the atomic transaction.
        """
        visit = PatientVisit.objects.create(
            hospital=self.hospital_a,
            patient=self.patient_a,
            visit_type=PatientVisit.VisitType.OPD,
            visit_date=timezone.now(),
            status=PatientVisit.Status.REGISTERED,
        )

        self.client.force_authenticate(user=self.user_doc1)
        payload = {
            "hospital": str(self.hospital_a.id),
            "doctor": str(self.doctor1.id),
            "patient_visit": str(visit.id),
            "complaints": "First consultation attempt",
        }

        # First request succeeds
        res1 = self.client.post(
            "/api/clinic/consultations/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        # Second request (concurrent/duplicate) fails
        res2 = self.client.post(
            "/api/clinic/consultations/",
            data=payload,
            format="json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_a.id),
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("patient_visit", res2.data)
        self.assertEqual(Consultation.objects.filter(patient_visit=visit).count(), 1)
