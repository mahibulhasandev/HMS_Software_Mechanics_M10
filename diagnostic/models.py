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


class DiagnosticTest(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    category = models.ForeignKey(
        TestCategory,
        on_delete=models.CASCADE,
        related_name="diagnostic_tests",
    )
    test_code = models.TextField()
    name = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    sample_type = models.TextField()
    turnaround_hours = models.IntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "diagnostic_tests"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "test_code"],
                name="uq_diagnostic_tests_hospital_code",
            ),
        ]

    def __str__(self):
        return f"{self.test_code} - {self.name}"


class TestOrder(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    status = models.TextField(default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "test_orders"

    def __str__(self):
        return str(self.id)


class TestOrderItem(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    test_order = models.ForeignKey(
        TestOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    diagnostic_test = models.ForeignKey(
        DiagnosticTest,
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    processed_by_hospital_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )
    price_at_order = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.TextField()
    sample_collected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "test_order_items"

    def __str__(self):
        return f"{self.id} - {self.status}"


class TestResult(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    test_order_item = models.ForeignKey(
        TestOrderItem,
        on_delete=models.CASCADE,
        related_name="results",
    )
    entered_by_hospital_user_id = models.UUIDField(db_index=True)
    parameter_name = models.TextField()
    result_value = models.TextField()
    unit = models.TextField(blank=True)
    reference_range = models.TextField(blank=True)
    flag = models.TextField(blank=True)

    class Meta:
        db_table = "test_results"

    def __str__(self):
        return f"{self.parameter_name}: {self.result_value}"


class DiagnosticReport(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    test_order = models.OneToOneField(
        TestOrder,
        on_delete=models.CASCADE,
        related_name="diagnostic_report",
    )
    verified_by_hospital_user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
    )
    report_number = models.TextField()
    summary = models.TextField(blank=True)
    status = models.TextField()
    verified_at = models.DateTimeField(null=True, blank=True)
    file_url = models.TextField(blank=True)

    class Meta:
        db_table = "diagnostic_reports"

    def __str__(self):
        return self.report_number