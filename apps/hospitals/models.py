
import uuid

from django.db import models


class Hospital(models.Model):

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    registration_number = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )

    name = models.CharField(max_length=255)
    address = models.TextField()

    phone = models.CharField(max_length=20)
    email = models.EmailField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    timezone = models.CharField(
        max_length=50,
        default="Asia/Dhaka",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hospitals"
        ordering = ["name"]
        verbose_name = "Hospital"
        verbose_name_plural = "Hospitals"

    def __str__(self):
        return f"{self.name} ({self.registration_number})"
