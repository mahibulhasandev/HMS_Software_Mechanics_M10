import uuid

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


# Phone Number Validator consistent with existing apps
phone_validator = RegexValidator(
    regex=r"^\+?[0-9]{7,20}$",
    message="Enter a valid phone number.",
)


# ==============================================================================
# USER MANAGER
# ==============================================================================

class UserManager(BaseUserManager):
    """
    Custom user manager supporting email or phone as the unique identity.
    Email is the primary USERNAME_FIELD.
    """

    def create_user(self, email=None, phone=None, password=None, **extra_fields):
        if not email and not phone:
            raise ValueError("The User must have an email address or phone number.")

        if email:
            email = self.normalize_email(email)
            extra_fields["email"] = email
        if phone:
            extra_fields["phone"] = phone

        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(**extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email=email, password=password, **extra_fields)


# ==============================================================================
# 1. USER
# ==============================================================================

class User(AbstractBaseUser, PermissionsMixin):
    """
    Central authenticated identity across all hospitals.
    Uses UUID primary key and supports email/phone login.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )

    phone = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        validators=[phone_validator],
    )

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            # Ensure at least one identity field (email or phone) is provided
            models.CheckConstraint(
                condition=models.Q(email__isnull=False) | models.Q(phone__isnull=False),
                name="ck_user_email_or_phone_required",
            ),
        ]

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else (self.email or self.phone or str(self.id))

    def __str__(self):
        return self.email or self.phone or str(self.id)


# ==============================================================================
# 2. CENTRAL DEPARTMENT
# ==============================================================================

class DepartmentType(models.TextChoices):
    CLINICAL = "clinical", "Clinical"
    NURSING = "nursing", "Nursing"
    PHARMACY = "pharmacy", "Pharmacy"
    DIAGNOSTIC = "diagnostic", "Diagnostic / Laboratory"
    ACCOUNTING = "accounting", "Accounting & Finance"
    ADMINISTRATIVE = "administrative", "Administrative & Management"
    SUPPORT = "support", "Support & Maintenance"


class Department(models.Model):
    """
    Enterprise-wide Department entity anchored to a Hospital tenant.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="departments",
    )

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, blank=True)
    department_type = models.CharField(
        max_length=30,
        choices=DepartmentType.choices,
        default=DepartmentType.CLINICAL,
    )

    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "departments"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "name"],
                name="uq_department_hospital_name",
            ),
        ]
        indexes = [
            models.Index(fields=["hospital", "is_active"], name="dept_hosp_active_idx"),
            models.Index(fields=["hospital", "department_type"], name="dept_hosp_type_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.hospital.name if hasattr(self, 'hospital') else self.hospital_id})"


# ==============================================================================
# 3. EMPLOYEE
# ==============================================================================

class EmployeeRole(models.TextChoices):
    HOSPITAL_ADMIN = "hospital_admin", "Hospital Admin"
    DOCTOR = "doctor", "Doctor"
    NURSE = "nurse", "Nurse"
    RECEPTIONIST = "receptionist", "Receptionist"
    PHARMACIST = "pharmacist", "Pharmacist"
    LAB_TECHNICIAN = "lab_technician", "Laboratory Technician"
    ACCOUNTANT = "accountant", "Accountant"
    BLOOD_BANK_STAFF = "blood_bank_staff", "Blood Bank Staff"
    GENERAL_STAFF = "general_staff", "General Staff"


class EmploymentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ON_LEAVE = "on_leave", "On Leave"
    SUSPENDED = "suspended", "Suspended"
    RESIGNED = "resigned", "Resigned"
    TERMINATED = "terminated", "Terminated"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Employee(models.Model):
    """
    Employment contract linking a User to a specific Hospital and Department.
    A single User can hold multiple Employee records across different hospitals.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="employee_profiles",
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="employees",
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="employees",
        null=True,
        blank=True,
    )

    employee_id = models.CharField(max_length=50)
    designation = models.CharField(max_length=100)
    role = models.CharField(
        max_length=30,
        choices=EmployeeRole.choices,
        default=EmployeeRole.GENERAL_STAFF,
        db_index=True,
    )

    joining_date = models.DateField(default=timezone.localdate)
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        db_index=True,
    )

    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )

    approved_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_employees",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "employees"
        ordering = ["employee_id"]
        constraints = [
            # Exactly one employment profile per user per hospital
            models.UniqueConstraint(
                fields=["hospital", "user"],
                name="uq_employee_hospital_user",
            ),
            # Employee ID must be unique per hospital
            models.UniqueConstraint(
                fields=["hospital", "employee_id"],
                name="uq_employee_hospital_code",
            ),
        ]
        indexes = [
            models.Index(fields=["hospital", "role"], name="emp_hosp_role_idx"),
            models.Index(fields=["hospital", "approval_status"], name="emp_hosp_approval_idx"),
            models.Index(fields=["hospital", "employment_status"], name="emp_hosp_status_idx"),
        ]

    def clean(self):
        errors = {}

        # 1. Validate that the assigned Department belongs to the same Hospital
        if self.department_id and self.hospital_id:
            if self.department.hospital_id != self.hospital_id:
                errors["department"] = "Department must belong to the same hospital."

        # 2. Validate that the Approving Employee belongs to the same Hospital and has Admin role
        if self.approved_by_id and self.hospital_id:
            if self.approved_by.hospital_id != self.hospital_id:
                errors["approved_by"] = "Approving administrator must belong to the same hospital."
            elif self.approved_by.role != EmployeeRole.HOSPITAL_ADMIN:
                errors["approved_by"] = "Only an employee with Hospital Admin role can approve registrations."

        # 3. Cannot approve oneself
        if self.approved_by_id and self.pk and self.approved_by_id == self.pk:
            errors["approved_by"] = "An employee cannot approve their own registration."

        # 4. If approved, approval timestamp must be present
        if self.approval_status == ApprovalStatus.APPROVED and not self.approved_at:
            self.approved_at = timezone.now()

        # 5. If rejected or pending, approved_at should be cleared
        if self.approval_status != ApprovalStatus.APPROVED:
            self.approved_at = None

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.employee_id} - {self.user.full_name} ({self.role})"
