
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
    )

    name = models.CharField(max_length=255)
    address = models.TextField()

    phone = models.CharField(max_length=20)
    email = models.EmailField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    timezone = models.CharField(
        max_length=50,
        default="Asia/Dhaka",
    )

    class Meta:
        db_table = "hospitals"
        ordering = ["name"]

    def __str__(self):
        return self.name
