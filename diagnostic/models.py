import uuid
from django.db import models


class TestCategory(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    name = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "test_categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "name"],
                name="uq_test_categories_hospital_name",
            )
        ]

    def __str__(self):
        return self.name