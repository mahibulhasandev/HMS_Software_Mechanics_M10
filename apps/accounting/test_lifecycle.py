
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account,
    Invoice,
    InvoiceItem,
    InvoiceItemStatus,
    Payment,
)
from apps.accounting.services import (
    issue_invoice,
    void_invoice,
)


class InvoiceLifecycleTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.other_hospital_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number="INV-LIFECYCLE-001",
            subtotal=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            status="draft",
            issued_at=timezone.now(),
        )

    def add_item(self, amount="500.00", status="active"):
        return InvoiceItem.objects.create(
            hospital_id=self.hospital_id,
            invoice=self.invoice,
            department_id=uuid.uuid4(),
            description="Doctor Consultation",
            quantity=1,
            unit_price=Decimal(amount),
            line_total=Decimal(amount),
            status=status,
        )

    def add_pending_payment(self):
        account_type = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )[0][0]

        account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Cash Account",
            account_type=account_type,
            account_number="LC-TEST-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        return Payment.objects.create(
            hospital_id=self.hospital_id,
            invoice=self.invoice,
            account=account,
            received_by_hospital_user_id=self.user_id,
            amount=Decimal("100.00"),
            method="cash",
            kind="payment",
            status="pending",
            reference_no="LC-PAY-001",
            paid_at=timezone.now(),
        )

    # 1. Draft invoice becomes issued.
    def test_issue_invoice_success(self):

        self.add_item("500.00")
        self.add_item("300.00")

        self.invoice.subtotal = Decimal("100.00")
        self.invoice.discount = Decimal("100.00")
        self.invoice.total = Decimal("0.00")

        self.invoice.save(
            update_fields=["subtotal", "discount", "total"]
        )

        issue_invoice(
            invoice_id=self.invoice.id,
            hospital_id=self.hospital_id,
        )

        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice.status, "issued")
        self.assertEqual(
            self.invoice.subtotal, Decimal("800.00")
        )
        self.assertEqual(
            self.invoice.discount, Decimal("100.00")
        )
        self.assertEqual(
            self.invoice.total, Decimal("700.00")
        )
        self.assertEqual(
            self.invoice.amount_paid, Decimal("0.00")
        )

    # 2. Empty invoice cannot be issued.
    def test_issue_empty_invoice_rejected(self):
        with self.assertRaises(ValidationError):
            issue_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.hospital_id,
            )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "draft")

    # 3. Non-draft invoice cannot be reissued.
    def test_issue_non_draft_rejected(self):
        self.add_item()

        self.invoice.status = "issued"
        self.invoice.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            issue_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.hospital_id,
            )

    # 4. Invalid discount blocks issuing.
    def test_issue_invalid_discount_rejected(self):

        self.add_item("100.00")

        # The stored row is valid, but the actual item
        # subtotal cannot support the stored discount.

        self.invoice.subtotal = Decimal("200.00")
        self.invoice.discount = Decimal("200.00")
        self.invoice.total = Decimal("0.00")

        self.invoice.save(
            update_fields=["subtotal", "discount", "total"]
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Discount cannot exceed subtotal.",
        ):

            issue_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.hospital_id,
            )

        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice.status, "draft")
        self.assertEqual(
            self.invoice.subtotal, Decimal("200.00")
        )
        self.assertEqual(
            self.invoice.total, Decimal("0.00")
        )

    # 5. Invoice with paid amount cannot be issued.
    def test_issue_with_paid_amount_rejected(self):

        from unittest.mock import patch

        self.add_item()

        # Simulate an inconsistent invoice returned to
        # the service without persisting an invalid row.

        self.invoice.amount_paid = Decimal("100.00")

        with patch.object(
            Invoice.objects,
            "select_for_update",
        ) as locked:

            locked.return_value.get.return_value = (
                self.invoice
            )

            with self.assertRaisesMessage(
                ValidationError,
                "Cannot issue an invoice with payment history.",
            ):

                issue_invoice(
                    invoice_id=self.invoice.id,
                    hospital_id=self.hospital_id,
                )

        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice.status, "draft")
        self.assertEqual(
            self.invoice.amount_paid, Decimal("0.00")
        )

    # 6. Payment history blocks issuing.
    def test_issue_with_payment_history_rejected(self):
        self.add_item()
        self.add_pending_payment()

        with self.assertRaises(ValidationError):
            issue_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.hospital_id,
            )

    # 7. Draft invoice can be voided.
    def test_void_draft_invoice(self):
        self.add_item()

        void_invoice(
            invoice_id=self.invoice.id,
            hospital_id=self.hospital_id,
        )

        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice.status, "voided")
        self.assertEqual(self.invoice.items.count(), 1)

    # 8. Unpaid issued invoice can be voided.
    def test_void_issued_invoice(self):
        self.add_item()

        issue_invoice(
            invoice_id=self.invoice.id,
            hospital_id=self.hospital_id,
        )

        void_invoice(
            invoice_id=self.invoice.id,
            hospital_id=self.hospital_id,
        )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "voided")

    # 9. Paid, partial and voided invoices are rejected.
    def test_void_invalid_status_rejected(self):

        for status, paid in (

            ("partially_paid", "100.00"),

            ("paid", "500.00"),

            ("voided", "0.00"),

        ):

            with self.subTest(status=status):

                self.invoice.subtotal = Decimal("500.00")
                self.invoice.discount = Decimal("0.00")
                self.invoice.total = Decimal("500.00")
                self.invoice.amount_paid = Decimal(paid)
                self.invoice.status = status

                self.invoice.save(
                    update_fields=[
                        "subtotal",
                        "discount",
                        "total",
                        "amount_paid",
                        "status",
                    ]
                )

                with self.assertRaisesMessage(
                    ValidationError,
                    "Only draft or issued invoices can be voided.",
                ):

                    void_invoice(
                        invoice_id=self.invoice.id,
                        hospital_id=self.hospital_id,
                    )

                self.invoice.refresh_from_db()

                self.assertEqual(
                    self.invoice.status, status
                )

                self.assertEqual(
                    self.invoice.amount_paid,
                    Decimal(paid),
                )

    # 10. Payment history prevents voiding.
    def test_void_with_payment_history_rejected(self):
        self.invoice.status = "issued"
        self.invoice.save(update_fields=["status"])

        self.add_pending_payment()

        with self.assertRaises(ValidationError):
            void_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.hospital_id,
            )

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, "issued")

    # 11. Another hospital cannot modify invoice.
    def test_cross_hospital_lifecycle_rejected(self):
        with self.assertRaises(Invoice.DoesNotExist):
            issue_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.other_hospital_id,
            )

        with self.assertRaises(Invoice.DoesNotExist):
            void_invoice(
                invoice_id=self.invoice.id,
                hospital_id=self.other_hospital_id,
            )