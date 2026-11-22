import uuid

from django.db import models
from django.db.models import Q


class Doctor(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="doctors",
    )

    # Temporary reference.
    # Later integrate with employees.Employee
    employee_id = models.UUIDField(unique=True)

    employee_type = models.CharField(
        max_length=50,
        default="doctor",
    )

    license_number = models.CharField(max_length=100)
    specialization = models.CharField(max_length=255)

    consultation_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    class Meta:
        db_table = "doctors"
        ordering = ["specialization", "license_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "license_number"],
                name="uq_doctor_hospital_license",
            ),
            models.CheckConstraint(
                condition=Q(consultation_fee__gte=0),
                name="doctor_consultation_fee_nonnegative",
            ),
        ]

    def __str__(self):
        return f"Dr. ({self.specialization}) - {self.license_number}"
