
import uuid
from datetime import date
from decimal import Decimal

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from apps.accounting.models import (
    Account,
    Expense,
    ExpenseCategory,
    Transaction,
)


class LedgerSecurityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        hospital_id = uuid.uuid4()

        account = Account.objects.create(
            hospital_id=hospital_id,
            name="Test Cash Account",
            account_type="cash",
            account_number="TEST-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        category = ExpenseCategory.objects.create(
            hospital_id=hospital_id,
            name="Test Expense Category",
        )

        expense = Expense.objects.create(
            hospital_id=hospital_id,
            expense_category=category,
            account=account,
            amount=Decimal("100.00"),
            expense_date=date.today(),
            description="Test Expense",
            status="paid",
        )

        cls.ledger = Transaction.objects.create(
            hospital_id=hospital_id,
            account=account,
            expense_category=category,
            expense=expense,
            transaction_type="expense",
            amount=Decimal("100.00"),
            transaction_date=date.today(),
            description="Original Ledger Entry",
        )

    def test_insert_allowed(self):
        self.assertTrue(
            Transaction.objects.filter(
                pk=self.ledger.pk
            ).exists()
        )

    def test_update_blocked(self):
        with self.assertRaisesMessage(
            DatabaseError,
            "Transactions are append-only"
        ):
            with transaction.atomic():
                Transaction.objects.filter(
                    pk=self.ledger.pk
                ).update(description="Modified")

    def test_delete_blocked(self):
        with self.assertRaisesMessage(
            DatabaseError,
            "Transactions are append-only"
        ):
            with transaction.atomic():
                Transaction.objects.filter(
                    pk=self.ledger.pk
                ).delete()

    def test_truncate_blocked(self):
        with self.assertRaisesMessage(
            DatabaseError,
            "Transactions are append-only"
        ):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "TRUNCATE TABLE transactions"
                    )
