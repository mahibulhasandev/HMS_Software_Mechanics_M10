
import uuid

from django.db import models


# ==========================================================
# CLINIC DEPARTMENT
# Hospital → Clinic → OPD Management
# ==========================================================


class DoctorSchedule(models.Model):
    """
    Doctor's weekly OPD schedule.

    TODO: [DOCTOR APP INTEGRATION]
    Uncomment the doctor ForeignKey after Doctor model is ready.
    """

    class Weekday(models.IntegerChoices):
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="clinic_doctor_schedules",
    )

    # TODO: [DOCTOR APP INTEGRATION]
    # Uncomment after apps.doctors is registered.
    #
    # doctor = models.ForeignKey(
    #     "doctors.Doctor",
    #     on_delete=models.PROTECT,
    #     related_name="clinic_schedules",
    # )

    weekday = models.IntegerField(
        choices=Weekday.choices,
    )

    start_time = models.TimeField()
    end_time = models.TimeField()

    slot_minutes = models.PositiveSmallIntegerField(
        default=15,
    )

    max_patients = models.PositiveSmallIntegerField(
        default=1,
    )

    valid_from = models.DateField()
    valid_to = models.DateField()

    is_available = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "clinic_doctor_schedules"
        ordering = ["weekday", "start_time"]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="clinic_schedule_valid_time",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_to__gte=models.F("valid_from")),
                name="clinic_schedule_valid_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(slot_minutes__in=[15, 30, 45]),
                name="clinic_schedule_valid_slot",
            ),
        ]

        indexes = [
            models.Index(
                fields=["hospital", "weekday"],
                name="clinic_schedule_day_idx",
            ),
        ]

    def __str__(self):
        return f"Schedule - {self.weekday} - {self.start_time}"


# ==========================================================
# APPOINTMENT
# Patient appointment booking and management
# ==========================================================


class Appointment(models.Model):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CHECKED_IN = "checked_in", "Checked In"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No Show"

    class BookingSource(models.TextChoices):
        RECEPTION = "reception", "Reception"
        ONLINE = "online", "Online"
        PHONE = "phone", "Phone"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="clinic_appointments",
    )

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="clinic_appointments",
    )

    # TODO: [DOCTOR APP INTEGRATION]
    # Uncomment after Doctor model is ready.
    #
    # doctor = models.ForeignKey(
    #     "doctors.Doctor",
    #     on_delete=models.PROTECT,
    #     related_name="clinic_appointments",
    # )

    patient_visit = models.OneToOneField(
        "patients.PatientVisit",
        on_delete=models.PROTECT,
        related_name="appointment",
        null=True,
        blank=True,
    )

    appointment_date = models.DateField()
    start_time = models.TimeField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    booking_source = models.CharField(
        max_length=20,
        choices=BookingSource.choices,
        default=BookingSource.RECEPTION,
    )

    reason = models.TextField(
        blank=True,
    )

    cancellation_reason = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "clinic_appointments"
        ordering = ["-appointment_date", "-start_time"]

        indexes = [
            models.Index(
                fields=["hospital", "appointment_date", "status"],
                name="clinic_appt_date_status_idx",
            ),
            models.Index(
                fields=["hospital", "patient"],
                name="clinic_appt_patient_idx",
            ),
        ]

    def __str__(self):
        return f"Appointment - {self.patient} - {self.appointment_date}"


# ==========================================================
# CONSULTATION
# Doctor's patient consultation
# ==========================================================


class Consultation(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="clinic_consultations",
    )

    patient_visit = models.ForeignKey(
        "patients.PatientVisit",
        on_delete=models.PROTECT,
        related_name="clinic_consultations",
    )

    # TODO: [DOCTOR APP INTEGRATION]
    # Uncomment after Doctor model is ready.
    #
    # doctor = models.ForeignKey(
    #     "doctors.Doctor",
    #     on_delete=models.PROTECT,
    #     related_name="clinic_consultations",
    # )

    appointment = models.OneToOneField(
        "clinic.Appointment",
        on_delete=models.PROTECT,
        related_name="consultation",
        null=True,
        blank=True,
    )

    complaints = models.TextField()
    examination_notes = models.TextField(blank=True)
    advice = models.TextField(blank=True)

    follow_up_date = models.DateField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "clinic_consultations"
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["hospital", "patient_visit"],
                name="clinic_consult_visit_idx",
            ),
        ]

    def __str__(self):
        return f"Consultation - {self.patient_visit}"


# ==========================================================
# DIAGNOSIS
# Consultation diagnosis records
# ==========================================================


class Diagnosis(models.Model):

    class DiagnosisType(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        DIFFERENTIAL = "differential", "Differential"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="clinic_diagnoses",
    )

    consultation = models.ForeignKey(
        "clinic.Consultation",
        on_delete=models.PROTECT,
        related_name="diagnoses",
    )

    diagnosis_name = models.CharField(
        max_length=255,
    )

    icd_code = models.CharField(
        max_length=20,
        blank=True,
    )

    diagnosis_type = models.CharField(
        max_length=20,
        choices=DiagnosisType.choices,
        default=DiagnosisType.PRIMARY,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "clinic_diagnoses"
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["hospital", "diagnosis_type"],
                name="clinic_diag_type_idx",
            ),
        ]

    def __str__(self):
        return self.diagnosis_name


# ==========================================================
# PRESCRIPTION
# Doctor's prescription
# ==========================================================


class Prescription(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="clinic_prescriptions",
    )

    consultation = models.ForeignKey(
        "clinic.Consultation",
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )

    prescribed_at = models.DateTimeField(
        auto_now_add=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "clinic_prescriptions"
        ordering = ["-prescribed_at"]

    def __str__(self):
        return f"Prescription - {self.consultation}"


# ==========================================================
# PRESCRIPTION ITEM
# Medicine and dosage details
# ==========================================================


class PrescriptionItem(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="clinic_prescription_items",
    )

    prescription = models.ForeignKey(
        "clinic.Prescription",
        on_delete=models.PROTECT,
        related_name="items",
    )

    # TODO: [PHARMACY APP INTEGRATION]
    # Uncomment after Pharmacy app and Medicine model are ready.
    #
    # medicine = models.ForeignKey(
    #     "pharmacy.Medicine",
    #     on_delete=models.PROTECT,
    #     related_name="clinic_prescription_items",
    # )

    dosage = models.CharField(
        max_length=100,
    )

    frequency = models.CharField(
        max_length=100,
    )

    duration_days = models.PositiveSmallIntegerField()

    quantity = models.PositiveIntegerField()

    instructions = models.TextField(
        blank=True,
    )

    class Meta:
        db_table = "clinic_prescription_items"

    def __str__(self):
        return f"Prescription Item - {self.dosage}"
