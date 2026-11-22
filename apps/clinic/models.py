
import uuid

from django.db import models
from django.db.models import Q, F


# ============================================================
# 1. DOCTOR SCHEDULE
# ============================================================

class DoctorSchedule(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="doctor_schedules",
    )

    # Temporary reference.
    # Later integrate with doctors.Doctor
    doctor_id = models.UUIDField()

    weekday = models.PositiveSmallIntegerField()

    start_time = models.TimeField()
    end_time = models.TimeField()

    slot_minutes = models.PositiveSmallIntegerField()
    max_patients = models.PositiveIntegerField()

    valid_from = models.DateField()
    valid_to = models.DateField()

    class Meta:
        db_table = "doctor_schedules"

        ordering = ["weekday", "start_time"]

        indexes = [
            models.Index(
                fields=["hospital", "doctor_id", "weekday"],
                name="clinic_doc_sched_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6),
                name="clinic_weekday_valid",
            ),
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="clinic_schedule_time_valid",
            ),
            models.CheckConstraint(
                condition=Q(slot_minutes__gt=0),
                name="clinic_slot_minutes_positive",
            ),
            models.CheckConstraint(
                condition=Q(max_patients__gt=0),
                name="clinic_max_patients_positive",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__gte=F("valid_from")),
                name="clinic_schedule_date_valid",
            ),
        ]

    def __str__(self):
        return (
            f"Doctor {self.doctor_id} - "
            f"Weekday {self.weekday} "
            f"({self.start_time} - {self.end_time})"
        )


# ============================================================
# 2. APPOINTMENT
# ============================================================

class Appointment(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="clinic_appointments",
    )

    # Shared entity references.
    # Later integrate with patients.Patient and doctors.Doctor.
    patient_id = models.UUIDField()
    doctor_id = models.UUIDField()

    # Temporary PatientVisit reference.
    patient_visit_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
    )

    appointment_date = models.DateField()

    start_time = models.TimeField()

    status = models.TextField()

    booking_source = models.TextField()

    class Meta:
        db_table = "appointments"

        ordering = ["appointment_date", "start_time"]

    def __str__(self):
        return (
            f"Appointment - {self.patient_id} "
            f"on {self.appointment_date}"
        )


# ============================================================
# 3. CONSULTATION
# ============================================================

class Consultation(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="clinic_consultations",
    )

    # Shared PatientVisit and Doctor references.
    patient_visit_id = models.UUIDField()
    doctor_id = models.UUIDField()

    # One appointment can have at most one linked consultation.
    appointment_id = models.UUIDField(
        null=True,
        blank=True,
        unique=True,
    )

    complaints = models.TextField(
        blank=True,
    )

    examination_notes = models.TextField(
        blank=True,
    )

    advice = models.TextField(
        blank=True,
    )

    follow_up_date = models.DateField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "consultations"

    def __str__(self):
        return f"Consultation - {self.id}"


# ============================================================
# 4. DIAGNOSIS
# ============================================================

class Diagnosis(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="clinic_diagnoses",
    )

    consultation = models.ForeignKey(
        "clinic.Consultation",
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )

    diagnosis_name = models.TextField()

    icd_code = models.TextField(
        blank=True,
    )

    diagnosis_type = models.TextField()

    class Meta:
        db_table = "diagnoses"

    def __str__(self):
        return self.diagnosis_name


# ============================================================
# 5. PRESCRIPTION
# ============================================================

class Prescription(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="clinic_prescriptions",
    )

    consultation = models.ForeignKey(
        "clinic.Consultation",
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )

    prescribed_at = models.DateTimeField()

    notes = models.TextField(
        blank=True,
    )

    class Meta:
        db_table = "prescriptions"

    def __str__(self):
        return f"Prescription - {self.id}"


# ============================================================
# 6. PRESCRIPTION ITEM
# ============================================================

class PrescriptionItem(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="clinic_prescription_items",
    )

    prescription = models.ForeignKey(
        "clinic.Prescription",
        on_delete=models.CASCADE,
        related_name="items",
    )

    # Temporary reference.
    # Later integrate with pharmacy.Medicine.
    medicine_id = models.UUIDField()

    dosage = models.TextField()

    frequency = models.TextField()

    duration_days = models.PositiveIntegerField()

    quantity = models.PositiveIntegerField()

    instructions = models.TextField(
        blank=True,
    )

    class Meta:
        db_table = "prescription_items"

        constraints = [
            models.CheckConstraint(
                condition=Q(duration_days__gt=0),
                name="clinic_rx_duration_positive",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="clinic_rx_quantity_positive",
            ),
        ]

    def __str__(self):
        return (
            f"Prescription Item - "
            f"{self.medicine_id}"
        )
