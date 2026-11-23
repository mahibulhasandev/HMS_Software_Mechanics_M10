
import uuid

from django.core.validators import RegexValidator
from django.db import models


phone_validator = RegexValidator(
    regex=r"^\+?[0-9]{7,20}$",
    message="Enter a valid phone number.",
)


class Patient(models.Model):

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    class BloodGroup(models.TextChoices):
        A_POSITIVE = "A+", "A+"
        A_NEGATIVE = "A-", "A-"
        B_POSITIVE = "B+", "B+"
        B_NEGATIVE = "B-", "B-"
        AB_POSITIVE = "AB+", "AB+"
        AB_NEGATIVE = "AB-", "AB-"
        O_POSITIVE = "O+", "O+"
        O_NEGATIVE = "O-", "O-"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        DECEASED = "deceased", "Deceased"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="patients",
    )

    patient_number = models.CharField(
        max_length=50,
    )

    first_name = models.CharField(
        max_length=100,
    )

    last_name = models.CharField(
        max_length=100,
        blank=True,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
    )

    blood_group = models.CharField(
        max_length=3,
        choices=BloodGroup.choices,
        blank=True,
    )

    phone = models.CharField(
        max_length=20,
        validators=[phone_validator],
    )

    email = models.EmailField(
        blank=True,
    )

    address = models.TextField(
        blank=True,
    )

    emergency_contact_name = models.CharField(
        max_length=150,
        blank=True,
    )

    emergency_contact_phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[phone_validator],
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "patients"

        ordering = [
            "first_name",
            "last_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "patient_number"],
                name="uq_patient_hospital_number",
            ),
            models.UniqueConstraint(
                fields=["hospital", "id"],
                name="uq_patient_hospital_id_id",
            ),
        ]

        indexes = [
            models.Index(
                fields=["hospital", "phone"],
                name="patient_hospital_phone_idx",
            ),
            models.Index(
                fields=["hospital", "status"],
                name="patient_hospital_status_idx",
            ),
            models.Index(
                fields=["hospital", "first_name", "last_name"],
                name="patient_hospital_name_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.patient_number} - "
            f"{self.first_name} {self.last_name}".strip()
        )


class PatientVisit(models.Model):

    class VisitType(models.TextChoices):
        OPD = "opd", "Outpatient"
        EMERGENCY = "emergency", "Emergency"
        FOLLOW_UP = "follow_up", "Follow Up"

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="patient_visits",
    )

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="visits",
    )

    visit_number = models.CharField(
        max_length=50,
    )

    visit_type = models.CharField(
        max_length=20,
        choices=VisitType.choices,
        default=VisitType.OPD,
    )

    visit_date = models.DateTimeField()

    chief_complaint = models.TextField(
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REGISTERED,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "patient_visits"

        ordering = [
            "-visit_date",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "visit_number"],
                name="uq_visit_hospital_number",
            ),
        ]

        indexes = [
            models.Index(
                fields=["hospital", "patient", "visit_date"],
                name="patient_visit_lookup_idx",
            ),
            models.Index(
                fields=["hospital", "status", "visit_date"],
                name="patient_visit_status_date_idx",
            ),
        ]

    def __str__(self):
        return f"{self.visit_number} - {self.patient}"
