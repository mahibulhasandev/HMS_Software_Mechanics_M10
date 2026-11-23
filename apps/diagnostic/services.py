import uuid
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    DiagnosticReport,
    DiagnosticTest,
    TestOrder,
    TestOrderItem,
    TestResult,
)


def generate_unique_order_number(hospital_id):
    """Generates an order_number unique per hospital_id."""
    while True:
        order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        if not TestOrder.objects.filter(
            hospital_id=hospital_id,
            order_number=order_number,
        ).exists():
            return order_number


def generate_unique_report_number():
    """Generates a unique report_number."""
    while True:
        report_number = f"RPT-{uuid.uuid4().hex[:8].upper()}"
        if not DiagnosticReport.objects.filter(report_number=report_number).exists():
            return report_number


@transaction.atomic
def create_test_order(
    *,
    hospital_id,
    patient_id,
    test_ids,
    priority="routine",
    patient_visit_id=None,
    ordered_by_doctor_id=None,
):
    """Creates a TestOrder and its corresponding TestOrderItem records."""
    unique_test_ids = list(dict.fromkeys(test_ids))
    if not unique_test_ids:
        raise ValidationError("At least one diagnostic test must be selected.")

    tests = list(
        DiagnosticTest.objects.filter(
            id__in=unique_test_ids,
            hospital_id=hospital_id,
            is_active=True,
        )
    )
    if len(tests) != len(unique_test_ids):
        raise ValidationError(
            "One or more selected tests are invalid or inactive for this hospital."
        )

    order = TestOrder.objects.create(
        hospital_id=hospital_id,
        patient_id=patient_id,
        patient_visit_id=patient_visit_id,
        ordered_by_doctor_id=ordered_by_doctor_id,
        order_number=generate_unique_order_number(hospital_id),
        status="pending",
        priority=priority or "routine",
    )

    items = [
        TestOrderItem(
            hospital_id=hospital_id,
            test_order=order,
            diagnostic_test=test,
            price_at_order=test.price,
            status="pending",
        )
        for test in tests
    ]
    TestOrderItem.objects.bulk_create(items)
    return order


@transaction.atomic
def mark_sample_collected(
    *,
    order_item_id,
    hospital_id,
    processed_by_hospital_user_id=None,
):
    """Marks a TestOrderItem sample as collected and updates order status."""
    item = (
        TestOrderItem.objects.select_related("test_order")
        .filter(id=order_item_id, hospital_id=hospital_id)
        .first()
    )
    if not item:
        raise ValidationError("Test order item not found for this hospital.")

    item.status = "sample_collected"
    item.sample_collected_at = timezone.now()
    if processed_by_hospital_user_id is not None:
        item.processed_by_hospital_user_id = processed_by_hospital_user_id
    item.save(
        update_fields=[
            "status",
            "sample_collected_at",
            "processed_by_hospital_user_id",
        ]
    )

    order = item.test_order
    if order.status == "pending":
        order.status = "in_progress"
        order.save(update_fields=["status"])

    return item


@transaction.atomic
def add_test_result(
    *,
    order_item_id,
    hospital_id,
    entered_by_hospital_user_id,
    parameter_name,
    result_value,
    unit="",
    reference_range="",
    flag="",
    mark_item_completed=False,
):
    """Adds a TestResult row for a TestOrderItem and ensures a draft DiagnosticReport exists."""
    item = (
        TestOrderItem.objects.select_related("test_order")
        .filter(id=order_item_id, hospital_id=hospital_id)
        .first()
    )
    if not item:
        raise ValidationError("Test order item not found for this hospital.")

    result = TestResult.objects.create(
        hospital_id=hospital_id,
        test_order_item=item,
        entered_by_hospital_user_id=entered_by_hospital_user_id,
        parameter_name=parameter_name,
        result_value=result_value,
        unit=unit or "",
        reference_range=reference_range or "",
        flag=flag or "",
    )

    if mark_item_completed:
        item.status = "completed"
        item.processed_by_hospital_user_id = entered_by_hospital_user_id
        item.save(update_fields=["status", "processed_by_hospital_user_id"])

    DiagnosticReport.objects.get_or_create(
        hospital_id=hospital_id,
        test_order=item.test_order,
        defaults={
            "report_number": generate_unique_report_number(),
            "status": "draft",
        },
    )

    return result


@transaction.atomic
def verify_diagnostic_report(
    *,
    report_id,
    hospital_id,
    verified_by_hospital_user_id,
    summary=None,
    file_url=None,
):
    """Verifies a DiagnosticReport after checking order items are completed."""
    report = (
        DiagnosticReport.objects.select_related("test_order")
        .prefetch_related("test_order__items")
        .filter(id=report_id, hospital_id=hospital_id)
        .first()
    )
    if not report:
        raise ValidationError("Diagnostic report not found for this hospital.")

    incomplete_items = report.test_order.items.exclude(status="completed").exists()
    if incomplete_items:
        raise ValidationError(
            "Cannot verify report while some test order items are still incomplete."
        )

    report.status = "verified"
    report.verified_at = timezone.now()
    report.verified_by_hospital_user_id = verified_by_hospital_user_id
    update_fields = ["status", "verified_at", "verified_by_hospital_user_id"]

    if summary is not None:
        report.summary = summary
        update_fields.append("summary")
    if file_url is not None:
        report.file_url = file_url
        update_fields.append("file_url")

    report.save(update_fields=update_fields)

    order = report.test_order
    order.status = "completed"
    order.save(update_fields=["status"])

    return report


def is_order_payment_cleared(order):
    """
    Checks whether payment for the order is cleared.
    Uses `is_paid` if present on TestOrder, or checks linked accounting invoices if available.
    """
    if hasattr(order, "is_paid"):
        return bool(order.is_paid)

    order_items = getattr(order, "items", None)
    if order_items is not None:
        invoices = []
        for item in order_items.all():
            inv_items = getattr(item, "invoice_items", None)
            if inv_items is not None:
                for inv_item in inv_items.all():
                    inv = getattr(inv_item, "invoice", None)
                    if inv is not None:
                        invoices.append(inv)
        if invoices:
            return all(
                str(getattr(inv, "status", "")).lower() == "paid"
                for inv in invoices
            )

    return False


def get_accessible_report(*, report_id, hospital_id):
    """
    Allows viewing final report only when report is verified AND payment is cleared.
    """
    report = (
        DiagnosticReport.objects.select_related("test_order")
        .filter(id=report_id, hospital_id=hospital_id)
        .first()
    )
    if not report:
        raise ValidationError("Diagnostic report not found for this hospital.")

    if str(report.status).lower() != "verified":
        raise PermissionDenied("Diagnostic report is not verified yet.")

    if not is_order_payment_cleared(report.test_order):
        raise PermissionDenied(
            "Payment is pending. Please clear the bill at Accounts to view the report."
        )

    return report