from decimal import Decimal
from uuid import uuid4

from django.db import (
    connection,
    transaction,
    IntegrityError,
)

from django.test import TestCase

from apps.accounting import test_transaction_http

from apps.accounting.models import (
    Expense,
    Transaction,
)


class FinancialIntegrityTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        test_transaction_http.TransactionHTTPTests.setUpTestData.__func__(cls)

        with connection.cursor() as cursor:

            cursor.execute(
                "GRANT SELECT, INSERT "
                "ON transactions TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT, UPDATE "
                "ON expenses TO hms_app"
            )

    def create_reversal(self, original, **overrides):

        data = {

            "hospital_id": original.hospital_id,

            "account_id": original.account_id,

            "income_category_id": (
                original.income_category_id
            ),

            "expense_category_id": (
                original.expense_category_id
            ),

            "reversed_transaction": original,

            "transaction_type": "reversal",

            "amount": original.amount,

            "transaction_date": self.today,

            "description": "Integrity test reversal",
        }

        data.update(overrides)

        return Transaction.objects.create(**data)

    def create_expense(self, keyed=True):

        return Expense.objects.create(

            hospital_id=self.hospital_a.pk,

            expense_category=self.category_a,

            account=self.account_a,

            amount=Decimal("500.00"),

            expense_date=self.today,

            description="Integrity test expense",

            status="draft",

            idempotency_key=(
                uuid4() if keyed else None
            ),

            request_fingerprint=(
                "a" * 64 if keyed else None
            ),
        )

    def assert_database_rejection(
        self,
        operation,
        constraint,
    ):

        with self.assertRaises(IntegrityError) as caught:

            with transaction.atomic():

                operation()

        self.assertEqual(

            caught.exception.__cause__.diag.constraint_name,

            constraint,
        )

    def assert_invalid_reversal(
        self,
        original,
        **overrides,
    ):

        before = Transaction.objects.count()

        self.assert_database_rejection(

            lambda: self.create_reversal(
                original,
                **overrides,
            ),

            "ck_txn_reversal_matches_original",
        )

        self.assertEqual(
            Transaction.objects.count(),
            before,
        )

    # Test 1
    def test_valid_reversals_allowed(self):

        for original in (
            self.income,
            self.refund,
            self.transaction_b,
        ):

            with self.subTest(original=original.pk):

                reversal = self.create_reversal(
                    original
                )

                self.assertEqual(
                    reversal.amount,
                    original.amount,
                )

                self.assertEqual(
                    reversal.account_id,
                    original.account_id,
                )

                self.assertEqual(
                    reversal.hospital_id,
                    original.hospital_id,
                )

    # Test 2
    def test_reversal_amount_mismatch_rejected(self):

        self.assert_invalid_reversal(

            self.income,

            amount=Decimal("999.00"),
        )

    # Test 3
    def test_reversal_account_mismatch_rejected(self):

        self.assert_invalid_reversal(

            self.income,

            account_id=self.account_a2.pk,
        )

    # Test 4
    def test_cross_hospital_reversal_rejected(self):

        self.assert_invalid_reversal(

            self.income,

            hospital_id=self.hospital_b.pk,

            account_id=self.account_b.pk,
        )

    # Test 5
    def test_reversal_of_reversal_rejected(self):

        self.assert_invalid_reversal(
            self.reversal
        )

    # Test 6
    def test_duplicate_reversal_rejected(self):

        before = Transaction.objects.count()

        self.assert_database_rejection(

            lambda: self.create_reversal(
                self.expense
            ),

            "transactions_reversed_transaction_id_key",
        )

        self.assertEqual(
            Transaction.objects.count(),
            before,
        )

    # Test 7
    def test_idempotency_identity_is_immutable(self):

        expense = self.create_expense()

        changes = (

            {"idempotency_key": uuid4()},

            {"idempotency_key": None},

            {"request_fingerprint": "b" * 64},

            {"request_fingerprint": None},

            {
                "idempotency_key": None,
                "request_fingerprint": None,
            },

            {"hospital_id": self.hospital_b.pk},

            {"id": uuid4()},
        )

        for change in changes:

            with self.subTest(change=change):

                self.assert_database_rejection(

                    lambda: Expense.objects.filter(
                        pk=expense.pk
                    ).update(**change),

                    "ck_expense_idempotency_immutable",
                )

        original_key = expense.idempotency_key

        expense.refresh_from_db()

        self.assertEqual(
            expense.idempotency_key,
            original_key,
        )

        self.assertEqual(
            expense.request_fingerprint,
            "a" * 64,
        )

        self.assertEqual(
            expense.hospital_id,
            self.hospital_a.pk,
        )

    # Test 8
    def test_legacy_expense_cannot_acquire_key(self):

        expense = self.create_expense(
            keyed=False
        )

        self.assert_database_rejection(

            lambda: Expense.objects.filter(
                pk=expense.pk
            ).update(
                idempotency_key=uuid4(),
                request_fingerprint="a" * 64,
            ),

            "ck_expense_idempotency_immutable",
        )

        expense.refresh_from_db()

        self.assertIsNone(expense.idempotency_key)

        self.assertIsNone(expense.request_fingerprint)

    # Test 9
    def test_normal_expense_status_update_allowed(self):

        for keyed in (True, False):

            with self.subTest(keyed=keyed):

                expense = self.create_expense(
                    keyed=keyed
                )

                original_key = expense.idempotency_key

                original_hash = (
                    expense.request_fingerprint
                )

                expense.status = "pending_approval"

                expense.save(
                    update_fields=["status"]
                )

                expense.refresh_from_db()

                self.assertEqual(
                    expense.status,
                    "pending_approval",
                )

                self.assertEqual(
                    expense.idempotency_key,
                    original_key,
                )

                self.assertEqual(
                    expense.request_fingerprint,
                    original_hash,
                )

    # Test 10
    def test_restricted_runtime_role_integrity(self):

        expense = self.create_expense()

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

            self.assert_invalid_reversal(

                self.income,

                amount=Decimal("999.00"),
            )

            self.assert_database_rejection(

                lambda: Expense.objects.filter(
                    pk=expense.pk
                ).update(
                    request_fingerprint="b" * 64
                ),

                "ck_expense_idempotency_immutable",
            )

            valid = self.create_reversal(
                self.income
            )

            self.assertEqual(
                valid.amount,
                self.income.amount,
            )

            updated = Expense.objects.filter(
                pk=expense.pk
            ).update(
                status="pending_approval"
            )

            self.assertEqual(updated, 1)

            # Restore role and session settings by rollback.

            transaction.set_rollback(True)
