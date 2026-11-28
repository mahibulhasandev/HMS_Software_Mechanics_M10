
import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account,
    Expense,
    ExpenseCategory,
    Invoice,
    Payment,
)

from apps.accounting.services import (
    approve_expense,
    create_expense,
    pay_expense,
    process_payment,
    process_refund,
    reverse_paid_expense,
    submit_expense_for_approval,
)


class PostedRecordProtectionTests(TestCase):

    def setUp(self):

        self.hospital_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

        account_type = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )[0][0]

        self.account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Protection Test Account",
            account_type=account_type,
            account_number=str(uuid.uuid4()),
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        self.category = ExpenseCategory.objects.create(
            hospital_id=self.hospital_id,
            name="Protection Test Category",
        )

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number=str(uuid.uuid4()),
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

    # ------------------------------------------------
    # FIXTURES
    # ------------------------------------------------

    def create_completed_payment(self):

        return process_payment(
            payment_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            invoice_id=self.invoice.id,
            account_id=self.account.id,
            received_by_hospital_user_id=self.user_id,
            amount="1000.00",
            method="cash",
            reference_no=str(uuid.uuid4()),
        )

    def create_completed_refund(self):

        original = self.create_completed_payment()

        return process_refund(
            refund_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            original_payment_id=original.id,
            received_by_hospital_user_id=self.user_id,
            amount="100.00",
            method="cash",
            reference_no=str(uuid.uuid4()),
        )

    def create_paid_expense(self):

        expense = create_expense(
            hospital_id=self.hospital_id,
            expense_category_id=self.category.id,
            account_id=self.account.id,
            amount="300.00",
            description="Protection Test Expense",
        )

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        approve_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
            approved_by_hospital_user_id=uuid.uuid4(),
        )

        pay_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        expense.refresh_from_db()

        return expense

    def create_reversed_expense(self):

        expense = self.create_paid_expense()

        reversal = reverse_paid_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
            return_reference="RETURN-PROTECTION-001",
            reason="Supplier returned the payment",
        )

        expense.refresh_from_db()

        return expense, reversal

    # ------------------------------------------------
    # DATABASE REJECTION HELPER
    # ------------------------------------------------

    def assert_db_rejects(self, operation):

        with self.assertRaises(IntegrityError):

            with transaction.atomic():

                operation()

    # ------------------------------------------------
    # 1. COMPLETED PAYMENT PROTECTION
    # ------------------------------------------------

    def test_completed_payment_amount_update_blocked(self):

        payment = self.create_completed_payment()

        self.assert_db_rejects(
            lambda: Payment.objects.filter(
                pk=payment.pk
            ).update(
                amount=Decimal("900.00")
            )
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.amount,
            Decimal("1000.00"),
        )

    def test_completed_payment_status_change_blocked(self):

        payment = self.create_completed_payment()

        self.assert_db_rejects(
            lambda: Payment.objects.filter(
                pk=payment.pk
            ).update(
                status="pending"
            )
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.status,
            "completed",
        )

    def test_completed_payment_delete_blocked(self):

        payment = self.create_completed_payment()

        self.assert_db_rejects(
            lambda: Payment.objects.filter(
                pk=payment.pk
            ).delete()
        )

        self.assertTrue(
            Payment.objects.filter(
                pk=payment.pk
            ).exists()
        )

    # ------------------------------------------------
    # 2. COMPLETED REFUND PROTECTION
    # ------------------------------------------------

    def test_completed_refund_update_blocked(self):

        refund = self.create_completed_refund()

        self.assert_db_rejects(
            lambda: Payment.objects.filter(
                pk=refund.pk
            ).update(
                amount=Decimal("90.00")
            )
        )

        refund.refresh_from_db()

        self.assertEqual(
            refund.amount,
            Decimal("100.00"),
        )

    def test_completed_refund_delete_blocked(self):

        refund = self.create_completed_refund()

        self.assert_db_rejects(
            lambda: Payment.objects.filter(
                pk=refund.pk
            ).delete()
        )

        self.assertTrue(
            Payment.objects.filter(
                pk=refund.pk
            ).exists()
        )

    # ------------------------------------------------
    # 3. PAID EXPENSE PROTECTION
    # ------------------------------------------------

    def test_paid_expense_amount_update_blocked(self):

        expense = self.create_paid_expense()

        self.assert_db_rejects(
            lambda: Expense.objects.filter(
                pk=expense.pk
            ).update(
                amount=Decimal("350.00")
            )
        )

        expense.refresh_from_db()

        self.assertEqual(
            expense.amount,
            Decimal("300.00"),
        )

    def test_paid_expense_status_change_blocked(self):

        expense = self.create_paid_expense()

        self.assert_db_rejects(
            lambda: Expense.objects.filter(
                pk=expense.pk
            ).update(
                status="approved"
            )
        )

        expense.refresh_from_db()

        self.assertEqual(
            expense.status,
            "paid",
        )

    def test_paid_expense_delete_blocked(self):

        expense = self.create_paid_expense()

        self.assert_db_rejects(
            lambda: Expense.objects.filter(
                pk=expense.pk
            ).delete()
        )

        self.assertTrue(
            Expense.objects.filter(
                pk=expense.pk
            ).exists()
        )

    def test_paid_expense_reversal_without_ledger_blocked(self):

        expense = self.create_paid_expense()

        self.assert_db_rejects(
            lambda: Expense.objects.filter(
                pk=expense.pk
            ).update(
                status="reversed"
            )
        )

        expense.refresh_from_db()

        self.assertEqual(
            expense.status,
            "paid",
        )

    # ------------------------------------------------
    # 4. VALID REVERSAL
    # ------------------------------------------------

    def test_valid_expense_reversal_allowed(self):

        expense, reversal = self.create_reversed_expense()

        self.assertEqual(
            expense.status,
            "reversed",
        )

        self.assertEqual(
            reversal.transaction_type,
            "reversal",
        )

        self.assertEqual(
            reversal.amount,
            Decimal("300.00"),
        )

    # ------------------------------------------------
    # 5. REVERSED EXPENSE PROTECTION
    # ------------------------------------------------

    def test_reversed_expense_update_blocked(self):

        expense, reversal = self.create_reversed_expense()

        self.assert_db_rejects(
            lambda: Expense.objects.filter(
                pk=expense.pk
            ).update(
                description="Tampered Expense"
            )
        )

        expense.refresh_from_db()

        self.assertEqual(
            expense.description,
            "Protection Test Expense",
        )

    def test_reversed_expense_delete_blocked(self):

        expense, reversal = self.create_reversed_expense()

        self.assert_db_rejects(
            lambda: Expense.objects.filter(
                pk=expense.pk
            ).delete()
        )

        self.assertTrue(
            Expense.objects.filter(
                pk=expense.pk
            ).exists()
        )