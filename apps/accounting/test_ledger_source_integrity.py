from decimal import Decimal
from uuid import uuid4

from django.db import (
    connection,
    transaction,
    IntegrityError,
)
from django.test import TestCase
from django.utils import timezone

from apps.accounting import test_transaction_http

from apps.accounting.models import (
    Payment,
    Expense,
    ExpenseCategory,
    Transaction,
)


class LedgerSourceIntegrityTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        test_transaction_http.TransactionHTTPTests.setUpTestData.__func__(cls)

        cls.category_a2 = ExpenseCategory.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Alternative Expense Category",
        )

    def create_payment(self, **overrides):

        data = {
            "hospital_id": self.hospital_a.pk,
            "invoice_id": self.income.payment.invoice_id,
            "account_id": self.account_a.pk,
            "received_by_hospital_user_id": self.actor,
            "amount": Decimal("100.00"),
            "method": "cash",
            "kind": "payment",
            "status": "completed",
            "reference_no": str(uuid4()),
            "paid_at": timezone.now(),
        }

        data.update(overrides)

        return Payment.objects.create(**data)

    def create_refund(self):

        return self.create_payment(
            kind="refund",
            amount=Decimal("50.00"),
            refunded_payment_id=self.income.payment_id,
        )

    def create_expense(self, **overrides):

        data = {
            "hospital_id": self.hospital_a.pk,
            "expense_category_id": self.category_a.pk,
            "account_id": self.account_a.pk,
            "amount": Decimal("100.00"),
            "expense_date": self.today,
            "description": "Ledger source test expense",
            "status": "paid",
            "approved_by_hospital_user_id": self.approver,
        }

        data.update(overrides)

        return Expense.objects.create(**data)

    def create_payment_ledger(self, payment, **overrides):

        data = {
            "hospital_id": payment.hospital_id,
            "account_id": payment.account_id,
            "payment_id": payment.pk,
            "transaction_type": (
                "refund"
                if payment.kind == "refund"
                else "income"
            ),
            "amount": payment.amount,
            "transaction_date": self.today,
            "description": "Payment source integrity test",
        }

        data.update(overrides)

        return Transaction.objects.create(**data)

    def create_expense_ledger(self, expense, **overrides):

        data = {
            "hospital_id": expense.hospital_id,
            "account_id": expense.account_id,
            "expense_category_id": expense.expense_category_id,
            "expense_id": expense.pk,
            "transaction_type": "expense",
            "amount": expense.amount,
            "transaction_date": self.today,
            "description": "Expense source integrity test",
        }

        data.update(overrides)

        return Transaction.objects.create(**data)

    def assert_database_rejection(
        self,
        operation,
        constraint,
    ):

        before = Transaction.objects.count()

        with self.assertRaises(IntegrityError) as caught:

            with transaction.atomic():

                operation()

        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            constraint,
        )

        self.assertEqual(
            Transaction.objects.count(),
            before,
        )

    # Test 1
    def test_valid_source_records_allowed(self):

        payment = self.create_payment()
        refund = self.create_refund()
        expense = self.create_expense()

        before = Transaction.objects.count()

        income = self.create_payment_ledger(payment)
        outflow = self.create_payment_ledger(refund)
        expense_entry = self.create_expense_ledger(expense)

        self.assertEqual(income.transaction_type, "income")
        self.assertEqual(outflow.transaction_type, "refund")
        self.assertEqual(expense_entry.transaction_type, "expense")

        self.assertEqual(income.amount, payment.amount)
        self.assertEqual(outflow.amount, refund.amount)
        self.assertEqual(expense_entry.amount, expense.amount)

        self.assertEqual(
            Transaction.objects.count(),
            before + 3,
        )

    # Test 2
    def test_payment_and_refund_amount_mismatch(self):

        for source in (
            self.create_payment(),
            self.create_refund(),
        ):

            with self.subTest(kind=source.kind):

                self.assert_database_rejection(

                    lambda: self.create_payment_ledger(
                        source,
                        amount=Decimal("999.00"),
                    ),

                    "ck_txn_payment_source_integrity",
                )

    # Test 3
    def test_payment_account_mismatch(self):

        payment = self.create_payment()

        self.assert_database_rejection(

            lambda: self.create_payment_ledger(
                payment,
                account_id=self.account_a2.pk,
            ),

            "ck_txn_payment_source_integrity",
        )

    # Test 4
    def test_payment_kind_mismatch(self):

        payment = self.create_payment()
        refund = self.create_refund()

        for source, invalid_type in (
            (payment, "refund"),
            (refund, "income"),
        ):

            with self.subTest(kind=source.kind):

                self.assert_database_rejection(

                    lambda: self.create_payment_ledger(
                        source,
                        transaction_type=invalid_type,
                    ),

                    "ck_txn_payment_source_integrity",
                )

    # Test 5
    def test_incomplete_payment_cannot_post(self):

        for status in (
            "pending",
            "failed",
            "voided",
        ):

            with self.subTest(status=status):

                payment = self.create_payment(
                    status=status
                )

                self.assert_database_rejection(

                    lambda: self.create_payment_ledger(
                        payment
                    ),

                    "ck_txn_payment_source_integrity",
                )

    # Test 6
    def test_cross_hospital_sources_rejected(self):

        payment = self.create_payment()
        expense = self.create_expense()

        self.assert_database_rejection(

            lambda: self.create_payment_ledger(
                payment,
                hospital_id=self.hospital_b.pk,
                account_id=self.account_b.pk,
            ),

            "ck_txn_payment_source_integrity",
        )

        self.assert_database_rejection(

            lambda: self.create_expense_ledger(
                expense,
                hospital_id=self.hospital_b.pk,
                account_id=self.account_b.pk,
                expense_category_id=self.category_b.pk,
            ),

            "ck_txn_expense_source_integrity",
        )

    # Test 7
    def test_expense_amount_mismatch(self):

        expense = self.create_expense()

        self.assert_database_rejection(

            lambda: self.create_expense_ledger(
                expense,
                amount=Decimal("999.00"),
            ),

            "ck_txn_expense_source_integrity",
        )

    # Test 8
    def test_expense_account_mismatch(self):

        expense = self.create_expense()

        self.assert_database_rejection(

            lambda: self.create_expense_ledger(
                expense,
                account_id=self.account_a2.pk,
            ),

            "ck_txn_expense_source_integrity",
        )

    # Test 9
    def test_expense_category_mismatch(self):

        expense = self.create_expense()

        self.assert_database_rejection(

            lambda: self.create_expense_ledger(
                expense,
                expense_category_id=self.category_a2.pk,
            ),

            "ck_txn_expense_source_integrity",
        )

    # Test 10
    def test_non_paid_expense_cannot_post(self):

        for status in (
            "draft",
            "pending_approval",
            "approved",
            "rejected",
            "reversed",
        ):

            with self.subTest(status=status):

                expense = self.create_expense(
                    status=status
                )

                self.assert_database_rejection(

                    lambda: self.create_expense_ledger(
                        expense
                    ),

                    "ck_txn_expense_source_integrity",
                )

    # Test 11
    def test_missing_sources_rejected(self):

        payment = self.create_payment()
        expense = self.create_expense()

        self.assert_database_rejection(

            lambda: self.create_payment_ledger(
                payment,
                payment_id=uuid4(),
            ),

            "ck_txn_payment_source_integrity",
        )

        self.assert_database_rejection(

            lambda: self.create_expense_ledger(
                expense,
                expense_id=uuid4(),
            ),

            "ck_txn_expense_source_integrity",
        )

    # Test 12
    def test_restricted_role_source_integrity(self):

        payment = self.create_payment()
        expense = self.create_expense()

        with connection.cursor() as cursor:

            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT ON payments, expenses TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT, INSERT ON transactions TO hms_app"
            )

        with transaction.atomic():

            with connection.cursor() as cursor:

                cursor.execute(
                    "SET LOCAL ROLE hms_app"
                )

                cursor.execute(
                    "SELECT set_config("
                    "'app.hospital_id', %s, true)",
                    [str(self.hospital_a.pk)],
                )

                cursor.execute("SELECT current_user")

                self.assertEqual(
                    cursor.fetchone()[0],
                    "hms_app",
                )

            self.assert_database_rejection(

                lambda: self.create_payment_ledger(
                    payment,
                    amount=Decimal("999.00"),
                ),

                "ck_txn_payment_source_integrity",
            )

            self.assert_database_rejection(

                lambda: self.create_expense_ledger(
                    expense,
                    account_id=self.account_a2.pk,
                ),

                "ck_txn_expense_source_integrity",
            )

            income = self.create_payment_ledger(payment)

            outflow = self.create_expense_ledger(expense)

            self.assertEqual(
                income.amount,
                payment.amount,
            )

            self.assertEqual(
                outflow.amount,
                expense.amount,
            )

            transaction.set_rollback(True)
