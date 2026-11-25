
import uuid

from django.db import models
from django.core.validators import RegexValidator, MinValueValidator
from django.core.exceptions import ValidationError


# ==========================================================
# PHONE VALIDATOR
# ==========================================================

phone_validator = RegexValidator(
    regex=r"^\+?[0-9]{7,20}$",
    message="Enter a valid phone number.",
)


# ==========================================================
# 1. DOCTOR DEPARTMENT
# ==========================================================

class DoctorDepartment(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="doctor_departments",
    )

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_departments"
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "name"],
                name="uq_doctor_dept_hospital_name",
            ),
        ]

        indexes = [
            models.Index(
                fields=["hospital", "is_active"],
                name="doc_dept_hosp_active_idx",
            ),
        ]

    def __str__(self):
        return self.name


# ==========================================================
# 2. DOCTOR SPECIALIZATION
# ==========================================================

class DoctorSpecialization(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="doctor_specializations",
    )

    department = models.ForeignKey(
        "doctors.DoctorDepartment",
        on_delete=models.PROTECT,
        related_name="specializations",
    )

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_specializations"
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "department", "name"],
                name="uq_doctor_spec_hosp_dept_name",
            ),
        ]

        indexes = [
            models.Index(
                fields=["hospital", "department", "is_active"],
                name="doc_spec_hosp_dept_idx",
            ),
        ]

    def clean(self):
        if self.hospital_id and self.department_id:
            if self.department.hospital_id != self.hospital_id:
                raise ValidationError({
                    "department": (
                        "Department must belong to the same hospital."
                    )
                })

    def __str__(self):
        return self.name


# ==========================================================
# 3. DOCTOR
# ==========================================================

class Doctor(models.Model):

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    class EmploymentType(models.TextChoices):
        FULL_TIME = "full_time", "Full Time"
        PART_TIME = "part_time", "Part Time"
        VISITING = "visiting", "Visiting"
        CONSULTANT = "consultant", "Consultant"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ON_LEAVE = "on_leave", "On Leave"
        SUSPENDED = "suspended", "Suspended"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="doctors",
    )

    department = models.ForeignKey(
        "doctors.DoctorDepartment",
        on_delete=models.PROTECT,
        related_name="doctors",
    )

    specialization = models.ForeignKey(
        "doctors.DoctorSpecialization",
        on_delete=models.PROTECT,
        related_name="doctors",
        null=True,
        blank=True,
    )

    employee = models.OneToOneField(
        "core.Employee",
        on_delete=models.PROTECT,
        related_name="doctor_profile",
        null=True,
        blank=True,
    )

    doctor_code = models.CharField(max_length=50)

    # Personal Information

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)

    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    phone = models.CharField(
        max_length=20,
        validators=[phone_validator],
    )

    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    profile_picture = models.ImageField(
        upload_to="doctors/profiles/",
        null=True,
        blank=True,
    )

    # Professional Information

    registration_number = models.CharField(
        max_length=100,
        blank=True,
    )

    qualifications = models.TextField(blank=True)

    experience_years = models.PositiveSmallIntegerField(
        default=0,
    )

    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )

    consultation_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    follow_up_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    joined_date = models.DateField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctors"
        ordering = ["first_name", "last_name"]

        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "doctor_code"],
                name="uq_doctor_hospital_code",
            ),
        ]

        indexes = [
            models.Index(
                fields=["hospital", "department", "status"],
                name="doctor_hosp_dept_status_idx",
            ),
            models.Index(
                fields=["hospital", "phone"],
                name="doctor_hospital_phone_idx",
            ),
        ]

    def clean(self):
        errors = {}

        if self.hospital_id and self.department_id:
            if self.department.hospital_id != self.hospital_id:
                errors["department"] = (
                    "Department must belong to the same hospital."
                )

        if self.hospital_id and self.specialization_id:
            if self.specialization.hospital_id != self.hospital_id:
                errors["specialization"] = (
                    "Specialization must belong to the same hospital."
                )

            elif self.specialization.department_id != self.department_id:
                errors["specialization"] = (
                    "Specialization must belong to the selected department."
                )

        if self.employee_id:
            if self.employee.hospital_id != self.hospital_id:
                errors["employee"] = (
                    "Linked employee must belong to the same hospital."
                )
            if self.employee.role != "doctor":
                errors["employee"] = (
                    "Linked employee must have the doctor role."
                )
            if self.employee.approval_status != "approved":
                errors["employee"] = (
                    "Linked employee must be approved."
                )
            if self.employee.employment_status != "active":
                errors["employee"] = (
                    "Linked employee must be active."
                )

        if errors:
            raise ValidationError(errors)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.doctor_code} - {self.full_name}"
