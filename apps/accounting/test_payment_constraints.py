
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import Account, Invoice, Payment


class PaymentReferenceConstraintTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        self.account, self.invoice = self.make_context(
            self.hospital_id
        )

    def make_context(self, hospital_id):
        account_type = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )[0][0]

        account = Account.objects.create(
            hospital_id=hospital_id,
            name="Test Cash Account",
            account_type=account_type,
            account_number=str(uuid.uuid4()),
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        invoice = Invoice.objects.create(
            hospital_id=hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number=str(uuid.uuid4()),
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

        return account, invoice

    def make_payment(
        self,
        *,
        hospital_id=None,
        account=None,
        invoice=None,
        kind="payment",
        method="card",
        status="completed",
        reference_no="TEST-REF",
        refunded_payment=None,
    ):
        return Payment.objects.create(
            hospital_id=(
                hospital_id
                if hospital_id is not None
                else self.hospital_id
            ),
            invoice=invoice or self.invoice,
            account=account or self.account,
            received_by_hospital_user_id=self.user_id,
            refunded_payment=refunded_payment,
            amount=Decimal("100.00"),
            method=method,
            kind=kind,
            status=status,
            reference_no=reference_no,
            paid_at=timezone.now(),
        )

    # 1. Duplicate completed card reference is blocked.
    def test_duplicate_card_reference_rejected(self):
        self.make_payment(reference_no="CARD-001")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_payment(
                    reference_no="CARD-001"
                )

        self.assertEqual(Payment.objects.count(), 1)

    # 2. Duplicate completed refund reference is blocked.
    def test_duplicate_refund_reference_rejected(self):
        original = self.make_payment(
            reference_no="ORIGINAL-001"
        )

        self.make_payment(
            kind="refund",
            method="mobile_wallet",
            reference_no="REFUND-001",
            refunded_payment=original,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_payment(
                    kind="refund",
                    method="mobile_wallet",
                    reference_no="REFUND-001",
                    refunded_payment=original,
                )

        self.assertEqual(Payment.objects.count(), 2)

    # 3. Other hospital may use the same reference.
    def test_same_reference_different_hospital(self):
        self.make_payment(reference_no="CARD-002")

        other_hospital = uuid.uuid4()
        other_account, other_invoice = (
            self.make_context(other_hospital)
        )

        self.make_payment(
            hospital_id=other_hospital,
            account=other_account,
            invoice=other_invoice,
            reference_no="CARD-002",
        )

        self.assertEqual(Payment.objects.count(), 2)

    # 4. Different payment methods have separate references.
    def test_same_reference_different_method(self):
        self.make_payment(
            method="card",
            reference_no="SHARED-001",
        )

        self.make_payment(
            method="bank_transfer",
            reference_no="SHARED-001",
        )

        self.assertEqual(Payment.objects.count(), 2)

    # 5. Cash payments are excluded from this constraint.
    def test_cash_reference_not_restricted(self):
        self.make_payment(
            method="cash",
            reference_no="CASH-001",
        )

        self.make_payment(
            method="cash",
            reference_no="CASH-001",
        )

        self.assertEqual(Payment.objects.count(), 2)

    # 6. Pending transactions are excluded.
    def test_pending_reference_not_restricted(self):
        self.make_payment(
            status="pending",
            reference_no="PENDING-001",
        )

        self.make_payment(
            status="pending",
            reference_no="PENDING-001",
        )

        self.assertEqual(Payment.objects.count(), 2)

    # 7. Payment and refund have separate reference scope.
    def test_payment_and_refund_reference_scope(self):
        original = self.make_payment(
            reference_no="SHARED-REF"
        )

        self.make_payment(
            kind="refund",
            reference_no="SHARED-REF",
            refunded_payment=original,
        )

        self.assertEqual(Payment.objects.count(), 2)