
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
from apps.accounting.services import process_payment


class PaymentProcessingTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.other_hospital_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        # Use an account type already supported by the model.
        account_types = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )
        self.account_type = account_types[0][0]

        self.account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Cash Account",
            account_type=self.account_type,
            account_number="ACC-TEST-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number="INV-PAY-001",
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

    def payment_data(self, **overrides):
        data = {
            "payment_id": uuid.uuid4(),
            "hospital_id": self.hospital_id,
            "invoice_id": self.invoice.id,
            "account_id": self.account.id,
            "received_by_hospital_user_id": self.user_id,
            "amount": "400.00",
            "method": "cash",
            "reference_no": str(uuid.uuid4()),
        }

        data.update(overrides)
        return data

    # 1. Partial payment creates a ledger entry.
    def test_partial_payment(self):
        payment = process_payment(
            **self.payment_data()
        )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("400.00"),
        )
        self.assertEqual(
            self.invoice.status,
            "partially_paid",
        )
        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.kind, "payment")

        ledger = Transaction.objects.get(
            payment=payment
        )

        self.assertEqual(
            ledger.amount,
            Decimal("400.00"),
        )
        self.assertEqual(
            ledger.transaction_type,
            "income",
        )
        self.assertEqual(
            ledger.hospital_id,
            self.hospital_id,
        )

    # 2. Two payments fully settle the invoice.
    def test_full_payment(self):
        process_payment(
            **self.payment_data(amount="400.00")
        )
        process_payment(
            **self.payment_data(amount="600.00")
        )

        self.invoice.refresh_from_db()

        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("1000.00"),
        )
        self.assertEqual(self.invoice.status, "paid")
        self.assertEqual(Payment.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)

    # 3. Retrying the same request is idempotent.
    def test_same_payment_retry(self):
        data = self.payment_data()

        first = process_payment(**data)
        second = process_payment(**data)

        self.assertEqual(first.id, second.id)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    # 4. Same payment ID with different data is rejected.
    def test_changed_retry_rejected(self):
        data = self.payment_data()
        process_payment(**data)

        changed = {
            **data,
            "amount": "500.00",
        }

        with self.assertRaises(ValidationError):
            process_payment(**changed)

        self.assertEqual(Payment.objects.count(), 1)

    # 5. Overpayment is rejected.
    def test_overpayment_rejected(self):
        with self.assertRaises(ValidationError):
            process_payment(
                **self.payment_data(
                    amount="1000.01"
                )
            )

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)

    # 6. Duplicate reference on the same invoice is rejected.
    def test_duplicate_reference_rejected(self):
        reference = "BANK-REF-001"

        process_payment(
            **self.payment_data(
                reference_no=reference
            )
        )

        with self.assertRaises(ValidationError):
            process_payment(
                **self.payment_data(
                    reference_no=reference
                )
            )

        self.assertEqual(Payment.objects.count(), 1)

    # 7. Draft invoices cannot receive payments.
    def test_draft_invoice_rejected(self):
        self.invoice.status = "draft"
        self.invoice.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            process_payment(
                **self.payment_data()
            )

        self.assertEqual(Payment.objects.count(), 0)

    # 8. Another hospital cannot access the invoice.
    def test_cross_hospital_invoice_rejected(self):
        with self.assertRaises(Invoice.DoesNotExist):
            process_payment(
                **self.payment_data(
                    hospital_id=self.other_hospital_id
                )
            )

        self.assertEqual(Payment.objects.count(), 0)

    # 9. Another hospital's account cannot be used.
    def test_cross_hospital_account_rejected(self):
        other_account = Account.objects.create(
            hospital_id=self.other_hospital_id,
            name="Other Hospital Cash",
            account_type=self.account_type,
            account_number="ACC-OTHER-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        with self.assertRaises(Account.DoesNotExist):
            process_payment(
                **self.payment_data(
                    account_id=other_account.id
                )
            )

        self.assertEqual(Payment.objects.count(), 0)

    # 10. A ledger error rolls back everything.
    def test_ledger_failure_rolls_back(self):
        with patch(
            "apps.accounting.services.Transaction.objects.create",
            side_effect=RuntimeError(
                "Simulated ledger failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                process_payment(
                    **self.payment_data()
                )

        self.invoice.refresh_from_db()

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(
            self.invoice.amount_paid,
            Decimal("0.00"),
        )
        self.assertEqual(self.invoice.status, "issued")
