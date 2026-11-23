import uuid
from django.db import models


# Test categories
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


# Diagnostic tests
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


# Test orders
class TestOrder(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hospital_id = models.UUIDField(db_index=True)
    patient_id = models.UUIDField(null=True, blank=True, db_index=True)
    patient_visit_id = models.UUIDField(null=True, blank=True, db_index=True)
    ordered_by_doctor_id = models.UUIDField(null=True, blank=True, db_index=True)
    order_number = models.TextField(default="")
    status = models.TextField(default="pending")
    priority = models.TextField(default="routine")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "test_orders"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "order_number"],
                name="uq_test_orders_hospital_order_number",
            )
        ]

    def __str__(self):
        return f"{self.order_number} ({self.id})"


# Test order items
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


# Test results
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


# Diagnostic reports
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