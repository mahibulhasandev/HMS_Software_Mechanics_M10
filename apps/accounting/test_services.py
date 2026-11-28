
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Invoice,
    InvoiceItem,
    InvoiceItemStatus,
)
from apps.accounting.services import recalculate_invoice_totals


class InvoiceCalculationTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.other_hospital_id = uuid.uuid4()

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            patient_id=None,
            patient_visit_id=None,
            created_by_hospital_user_id=uuid.uuid4(),
            invoice_number="INV-TEST-001",
            subtotal=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            status="draft",
            issued_at=timezone.now(),
        )

    def add_item(self, amount, status="active"):
        return InvoiceItem.objects.create(
            hospital_id=self.hospital_id,
            invoice=self.invoice,
            department_id=uuid.uuid4(),
            description="Test Service",
            quantity=1,
            unit_price=Decimal(str(amount)),
            line_total=Decimal(str(amount)),
            status=status,
        )

    def test_subtotal_and_discount_calculation(self):

        self.add_item("200.00")
        self.add_item("100.00")

        self.add_item(
            "500.00",
            status=InvoiceItemStatus.VOIDED,
        )

        # Initially valid invoice values. Recalculation
        # must update the subtotal using active items.

        self.invoice.subtotal = Decimal("200.00")
        self.invoice.discount = Decimal("50.00")
        self.invoice.total = Decimal("150.00")
        self.invoice.amount_paid = Decimal("100.00")
        self.invoice.status = "partially_paid"

        self.invoice.save()

        recalculate_invoice_totals(
            self.invoice.id,
            self.hospital_id,
        )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.subtotal, Decimal("300.00")
        )
        self.assertEqual(
            self.invoice.discount, Decimal("50.00")
        )
        self.assertEqual(
            self.invoice.total, Decimal("250.00")
        )
        self.assertEqual(
            self.invoice.amount_paid, Decimal("100.00")
        )
        self.assertEqual(
            self.invoice.status, "partially_paid"
        )

    def test_empty_invoice(self):
        recalculate_invoice_totals(
            self.invoice.id,
            self.hospital_id,
        )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.subtotal,
            Decimal("0.00"),
        )
        self.assertEqual(
            self.invoice.total,
            Decimal("0.00"),
        )

    def test_discount_exceeds_subtotal(self):

        self.add_item("100.00")

        self.invoice.subtotal = Decimal("150.00")
        self.invoice.discount = Decimal("150.00")
        self.invoice.total = Decimal("0.00")

        self.invoice.save(
            update_fields=["subtotal", "discount", "total"]
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Discount cannot exceed subtotal.",
        ):

            recalculate_invoice_totals(
                self.invoice.id,
                self.hospital_id,
            )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.subtotal, Decimal("150.00")
        )
        self.assertEqual(
            self.invoice.total, Decimal("0.00")
        )

    def test_paid_amount_exceeds_total(self):

        self.add_item("50.00")

        self.invoice.subtotal = Decimal("100.00")
        self.invoice.total = Decimal("100.00")
        self.invoice.amount_paid = Decimal("100.00")
        self.invoice.status = "paid"

        self.invoice.save(
            update_fields=[
                "subtotal",
                "total",
                "amount_paid",
                "status",
            ]
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Invoice total cannot be less than amount paid.",
        ):

            recalculate_invoice_totals(
                self.invoice.id,
                self.hospital_id,
            )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid, Decimal("100.00")
        )
        self.assertEqual(
            self.invoice.total, Decimal("100.00")
        )
        self.assertEqual(self.invoice.status, "paid")

    def test_voided_invoice_cannot_recalculate(self):
        self.invoice.status = "voided"
        self.invoice.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            recalculate_invoice_totals(
                self.invoice.id,
                self.hospital_id,
            )

    def test_wrong_hospital_cannot_access_invoice(self):
        with self.assertRaises(Invoice.DoesNotExist):
            recalculate_invoice_totals(
                self.invoice.id,
                self.other_hospital_id,
            )

# ============================================================
# INVOICE ITEM CREATION TESTS
# ============================================================

from apps.accounting.services import add_invoice_item


class InvoiceItemCreationTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.other_hospital_id = uuid.uuid4()
        self.department_id = uuid.uuid4()

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=uuid.uuid4(),
            invoice_number="INV-ITEM-001",
            subtotal=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            status="draft",
            issued_at=timezone.now(),
        )

    def add_item(self, **overrides):
        data = {
            "invoice_id": self.invoice.id,
            "hospital_id": self.hospital_id,
            "department_id": self.department_id,
            "description": "Doctor Consultation",
            "quantity": 2,
            "unit_price": "250.00",
        }

        data.update(overrides)

        return add_invoice_item(**data)

    # Test 1: Item creation and calculation
    def test_item_creation_updates_invoice(self):
        item = self.add_item()

        self.assertEqual(item.quantity, 2)
        self.assertEqual(
            item.line_total,
            Decimal("500.00")
        )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.subtotal,
            Decimal("500.00")
        )

        self.assertEqual(
            self.invoice.total,
            Decimal("500.00")
        )

        self.assertEqual(
            self.invoice.items.count(),
            1
        )

    # Test 2: Invalid quantity
    def test_invalid_quantity_rejected(self):
        for quantity in [0, -1, 1.5, True]:
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    self.add_item(quantity=quantity)

        self.assertEqual(InvoiceItem.objects.count(), 0)

    # Test 3: Invalid unit price
    def test_invalid_price_rejected(self):
        for price in ["-10.00", "12.345", "abc", "NaN"]:
            with self.subTest(price=price):
                with self.assertRaises(ValidationError):
                    self.add_item(unit_price=price)

        self.assertEqual(InvoiceItem.objects.count(), 0)

    # Test 4: Atomic rollback
    def test_failed_calculation_rolls_back_item(self):

        self.invoice.subtotal = Decimal("600.00")
        self.invoice.discount = Decimal("600.00")
        self.invoice.total = Decimal("0.00")

        self.invoice.save(
            update_fields=["subtotal", "discount", "total"]
        )

        before_count = InvoiceItem.objects.count()

        with self.assertRaisesMessage(
            ValidationError,
            "Discount cannot exceed subtotal.",
        ):

            self.add_item()

        self.assertEqual(
            InvoiceItem.objects.count(),
            before_count,
        )

        self.invoice.refresh_from_db()

        # The failed operation must preserve all
        # original invoice values.

        self.assertEqual(
            self.invoice.subtotal, Decimal("600.00")
        )
        self.assertEqual(
            self.invoice.discount, Decimal("600.00")
        )
        self.assertEqual(
            self.invoice.total, Decimal("0.00")
        )
        self.assertEqual(self.invoice.status, "draft")

    # Test 5: Wrong hospital
    def test_cross_hospital_item_creation_blocked(self):
        with self.assertRaises(Invoice.DoesNotExist):
            self.add_item(
                hospital_id=self.other_hospital_id
            )

        self.assertEqual(
            InvoiceItem.objects.count(),
            0
        )

    # Test 6: Only draft invoice accepts items
    def test_issued_invoice_rejects_new_items(self):
        self.invoice.status = "issued"
        self.invoice.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            self.add_item()

        self.assertEqual(
            InvoiceItem.objects.count(),
            0
        )