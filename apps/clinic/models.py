
import uuid

from django.db import models
from django.core.exceptions import ValidationError


class DoctorSchedule(models.Model):

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="doctor_schedules",
    )

    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.PROTECT,
        related_name="schedules",
    )

    weekday = models.IntegerField(choices=Weekday.choices)

    start_time = models.TimeField()
    end_time = models.TimeField()

    slot_minutes = models.PositiveSmallIntegerField(default=15)
    max_patients = models.PositiveSmallIntegerField(default=1)

    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    is_available = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clinic_doctor_schedules"
        ordering = ["weekday", "start_time"]
        indexes = [
            models.Index(fields=["hospital", "weekday"]),
            models.Index(fields=["doctor", "weekday"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="clinic_schedule_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(slot_minutes__in=[15, 30, 45]),
                name="clinic_schedule_valid_slot",
            ),
            models.CheckConstraint(
                condition=models.Q(max_patients__gte=1),
                name="clinic_schedule_positive_patients",
            ),
        ]

    def clean(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError("Valid To cannot be earlier than Valid From.")

        if self.doctor_id and self.hospital_id:
            if self.doctor.hospital_id != self.hospital_id:
                raise ValidationError("Doctor and hospital must match.")

    def __str__(self):
        return f"{self.doctor} - {self.get_weekday_display()}"


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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="appointments",
    )

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="appointments",
    )

    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.PROTECT,
        related_name="appointments",
    )

    patient_visit = models.OneToOneField(
        "patients.PatientVisit",
        on_delete=models.PROTECT,
        related_name="appointment",
        null=True,
        blank=True,
    )

    appointment_date = models.DateField()
    appointment_time = models.TimeField()

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

    reason = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clinic_appointments"
        ordering = ["-appointment_date", "appointment_time"]
        indexes = [
            models.Index(fields=["hospital", "appointment_date"]),
            models.Index(fields=["doctor", "appointment_date"]),
            models.Index(fields=["patient", "appointment_date"]),
            models.Index(fields=["status"]),
        ]

    def clean(self):
        if self.patient_id and self.hospital_id:
            if self.patient.hospital_id != self.hospital_id:
                raise ValidationError("Patient and hospital must match.")

        if self.doctor_id and self.hospital_id:
            if self.doctor.hospital_id != self.hospital_id:
                raise ValidationError("Doctor and hospital must match.")

        if self.patient_visit_id:
            if self.patient_visit.hospital_id != self.hospital_id:
                raise ValidationError("Visit and hospital must match.")

            if self.patient_visit.patient_id != self.patient_id:
                raise ValidationError("Visit must belong to this patient.")

    def __str__(self):
        return f"{self.patient} - {self.appointment_date}"


class Consultation(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="consultations",
    )

    patient_visit = models.ForeignKey(
        "patients.PatientVisit",
        on_delete=models.PROTECT,
        related_name="consultations",
    )

    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.PROTECT,
        related_name="consultations",
    )

    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.PROTECT,
        related_name="consultation",
        null=True,
        blank=True,
    )

    complaints = models.TextField(blank=True)
    examination_notes = models.TextField(blank=True)
    advice = models.TextField(blank=True)

    follow_up_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clinic_consultations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["hospital", "created_at"]),
            models.Index(fields=["doctor", "created_at"]),
        ]

    def clean(self):
        if self.patient_visit_id and self.hospital_id:
            if self.patient_visit.hospital_id != self.hospital_id:
                raise ValidationError("Visit and hospital must match.")

        if self.doctor_id and self.hospital_id:
            if self.doctor.hospital_id != self.hospital_id:
                raise ValidationError("Doctor and hospital must match.")

        if self.appointment_id:
            if self.appointment.hospital_id != self.hospital_id:
                raise ValidationError("Appointment and hospital must match.")

            if self.appointment.patient_id != self.patient_visit.patient_id:
                raise ValidationError("Appointment and visit patient must match.")

    def __str__(self):
        return f"Consultation - {self.patient_visit}"


class Diagnosis(models.Model):

    class DiagnosisType(models.TextChoices):
        PRIMARY = "primary", "Primary"
        SECONDARY = "secondary", "Secondary"
        DIFFERENTIAL = "differential", "Differential"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="diagnoses",
    )

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )

    diagnosis_name = models.CharField(max_length=255)
    icd_code = models.CharField(max_length=20, blank=True)

    diagnosis_type = models.CharField(
        max_length=20,
        choices=DiagnosisType.choices,
        default=DiagnosisType.PRIMARY,
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clinic_diagnoses"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["hospital", "diagnosis_type"]),
        ]

    def clean(self):
        if self.consultation_id and self.hospital_id:
            if self.consultation.hospital_id != self.hospital_id:
                raise ValidationError("Consultation and hospital must match.")

    def __str__(self):
        return self.diagnosis_name


class Prescription(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )

    consultation = models.ForeignKey(
        Consultation,
        on_delete=models.PROTECT,
        related_name="prescriptions",
    )

    prescribed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "clinic_prescriptions"
        ordering = ["-prescribed_at"]

    def clean(self):
        if self.consultation_id and self.hospital_id:
            if self.consultation.hospital_id != self.hospital_id:
                raise ValidationError("Consultation and hospital must match.")

    def __str__(self):
        return f"Prescription - {self.consultation}"


class PrescriptionItem(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="prescription_items",
    )

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )

    # Pharmacy Medicine FK will be added when pharmacy app is ready.
    medicine_id = models.UUIDField(null=True, blank=True)

    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration_days = models.PositiveSmallIntegerField()
    quantity = models.PositiveIntegerField()

    instructions = models.TextField(blank=True)

    class Meta:
        db_table = "clinic_prescription_items"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_days__gte=1),
                name="clinic_prescription_positive_duration",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="clinic_prescription_positive_quantity",
            ),
        ]

    def clean(self):
        if self.prescription_id and self.hospital_id:
            if self.prescription.hospital_id != self.hospital_id:
                raise ValidationError("Prescription and hospital must match.")

    def __str__(self):
        return f"{self.dosage} - {self.frequency}"
