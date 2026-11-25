
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account,
    Invoice,
    Payment,
    Transaction,
)
from apps.accounting.services import (
    process_payment,
    process_refund,
)


class RefundProcessingTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.other_hospital_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        account_type = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )[0][0]

        self.account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Refund Test Account",
            account_type=account_type,
            account_number="REF-ACC-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number="INV-REF-001",
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

        # Create a real completed payment and income ledger.
        self.original = process_payment(
            payment_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            invoice_id=self.invoice.id,
            account_id=self.account.id,
            received_by_hospital_user_id=self.user_id,
            amount="1000.00",
            method="cash",
            reference_no="ORIGINAL-PAY-001",
        )

    def refund_data(self, **overrides):
        data = {
            "refund_id": uuid.uuid4(),
            "hospital_id": self.hospital_id,
            "original_payment_id": self.original.id,
            "received_by_hospital_user_id": self.user_id,
            "amount": "300.00",
            "method": "cash",
            "reference_no": str(uuid.uuid4()),
        }

        data.update(overrides)
        return data

    def refund(self, **overrides):
        return process_refund(
            **self.refund_data(**overrides)
        )

    # 1. Partial refund
    def test_partial_refund(self):
        refund = self.refund(amount="300.00")

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("700.00"),
        )
        self.assertEqual(
            self.invoice.status,
            "partially_paid",
        )
        self.assertEqual(refund.kind, "refund")
        self.assertEqual(refund.status, "completed")
        self.assertEqual(
            refund.refunded_payment_id,
            self.original.id,
        )

        ledger = Transaction.objects.get(
            payment=refund
        )

        self.assertEqual(
            ledger.transaction_type,
            "refund",
        )
        self.assertEqual(
            ledger.amount,
            Decimal("300.00"),
        )

    # 2. Full refund
    def test_full_refund(self):
        self.refund(amount="1000.00")

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("0.00"),
        )
        self.assertEqual(
            self.invoice.status,
            "issued",
        )
        self.assertEqual(Transaction.objects.count(), 2)

    # 3. Multiple partial refunds
    def test_multiple_partial_refunds(self):
        self.refund(amount="300.00")
        self.refund(amount="200.00")

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("500.00"),
        )
        self.assertEqual(
            Payment.objects.filter(kind="refund").count(),
            2,
        )
        self.assertEqual(Transaction.objects.count(), 3)

    # 4. Over-refund protection
    def test_over_refund_rejected(self):
        self.refund(amount="700.00")

        with self.assertRaises(ValidationError):
            self.refund(amount="400.00")

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("300.00"),
        )
        self.assertEqual(Payment.objects.count(), 2)

    # 5. Same refund retry
    def test_same_refund_retry(self):
        data = self.refund_data()

        first = process_refund(**data)
        second = process_refund(**data)

        self.assertEqual(first.id, second.id)
        self.assertEqual(Payment.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)

    # 6. Changed request using same refund ID
    def test_changed_retry_rejected(self):
        data = self.refund_data()

        process_refund(**data)

        with self.assertRaises(ValidationError):
            process_refund(
                **{
                    **data,
                    "amount": "400.00",
                }
            )

        self.assertEqual(Payment.objects.count(), 2)

    # 7. Duplicate refund reference
    def test_duplicate_reference_rejected(self):
        self.refund(
            amount="100.00",
            reference_no="REF-001",
        )

        with self.assertRaises(ValidationError):
            self.refund(
                amount="100.00",
                reference_no="REF-001",
            )

        self.assertEqual(Payment.objects.count(), 2)

    # 8. Cross-hospital refund protection
    def test_cross_hospital_refund_rejected(self):
        with self.assertRaises(Payment.DoesNotExist):
            self.refund(
                hospital_id=self.other_hospital_id,
            )

        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    # 9. Invalid refund amounts
    def test_invalid_refund_amount_rejected(self):
        invalid_amounts = [
            "0.00",
            "-10.00",
            "10.001",
            "NaN",
            True,
            3.14,
        ]

        for amount in invalid_amounts:
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    self.refund(amount=amount)

        self.assertEqual(Payment.objects.count(), 1)

    # 10. Incomplete original payment
    def test_incomplete_original_payment_rejected(self):
        self.original.status = "pending"
        self.original.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            self.refund()

        self.assertEqual(
            Payment.objects.filter(kind="refund").count(),
            0,
        )

    # 11. Ledger failure must roll back refund
    def test_ledger_failure_rolls_back(self):
        with patch(
            "apps.accounting.services.Transaction.objects.create",
            side_effect=RuntimeError(
                "Simulated refund ledger failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                self.refund()

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("1000.00"),
        )
        self.assertEqual(self.invoice.status, "paid")

        # Only the original payment and ledger remain.
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    # 12. Database duplicate refund reference is handled.
    def test_database_duplicate_refund_reference_handled(self):
        reference = "WALLET-REF-DUP-001"

        # First invoice: completed electronic refund.
        first_refund = self.refund(
            amount="100.00",
            method="mobile_wallet",
            reference_no=reference,
        )

        self.assertEqual(first_refund.status, "completed")

        # Create a second invoice in the same hospital.
        second_invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number="INV-REF-002",
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

        # Make a completed payment for the second invoice.
        second_payment = process_payment(
            payment_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            invoice_id=second_invoice.id,
            account_id=self.account.id,
            received_by_hospital_user_id=self.user_id,
            amount="1000.00",
            method="cash",
            reference_no="SECOND-ORIGINAL-PAY",
        )

        # A second refund cannot reuse the electronic
        # reference, even for a different invoice.
        with self.assertRaises(ValidationError) as context:
            process_refund(
                refund_id=uuid.uuid4(),
                hospital_id=self.hospital_id,
                original_payment_id=second_payment.id,
                received_by_hospital_user_id=self.user_id,
                amount="200.00",
                method="mobile_wallet",
                reference_no=reference,
            )

        self.assertIn(
            "electronic transaction reference",
            str(context.exception),
        )

        # Original payments + first refund only.
        self.assertEqual(Payment.objects.count(), 3)
        self.assertEqual(Transaction.objects.count(), 3)

        # Failed refund must not change second invoice.
        second_invoice.refresh_from_db()

        self.assertEqual(
            second_invoice.amount_paid,
            Decimal("1000.00"),
        )
        self.assertEqual(second_invoice.status, "paid")