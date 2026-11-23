
import uuid
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account,
    Expense,
    ExpenseCategory,
    Transaction,
)
from apps.accounting.services import create_expense


class ExpenseCreationTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.other_hospital_id = uuid.uuid4()

        account_type = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )[0][0]

        self.account_type = account_type

        self.account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Cash Account",
            account_type=account_type,
            account_number="EXP-ACC-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        self.category = ExpenseCategory.objects.create(
            hospital_id=self.hospital_id,
            name="Utilities",
        )

    def expense_data(self, **overrides):
        data = {
            "hospital_id": self.hospital_id,
            "expense_category_id": self.category.id,
            "account_id": self.account.id,
            "amount": "5000.00",
            "description": "Electricity Bill",
        }

        data.update(overrides)
        return data

    # Test 1: Create a draft expense.
    def test_create_expense_success(self):
        expense = create_expense(
            **self.expense_data()
        )

        self.assertEqual(expense.status, "draft")
        self.assertEqual(
            expense.amount,
            Decimal("5000.00"),
        )
        self.assertEqual(
            expense.hospital_id,
            self.hospital_id,
        )
        self.assertEqual(
            expense.expense_category_id,
            self.category.id,
        )
        self.assertEqual(
            expense.account_id,
            self.account.id,
        )
        self.assertEqual(
            expense.expense_date,
            timezone.localdate(),
        )
        self.assertIsNone(
            expense.approved_by_hospital_user_id
        )

        self.assertEqual(Expense.objects.count(), 1)

        # Draft expense must not create a ledger entry.
        self.assertEqual(Transaction.objects.count(), 0)

    # Test 2: Invalid amounts are rejected.
    def test_invalid_amount_rejected(self):
        invalid_amounts = [
            "0.00",
            "-10.00",
            "12.345",
            "NaN",
            True,
            5.25,
        ]

        for amount in invalid_amounts:
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    create_expense(
                        **self.expense_data(
                            amount=amount
                        )
                    )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 3: Empty description is rejected.
    def test_empty_description_rejected(self):
        for description in ["", "   ", None]:
            with self.subTest(description=description):
                with self.assertRaises(ValidationError):
                    create_expense(
                        **self.expense_data(
                            description=description
                        )
                    )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 4: Invalid expense date is rejected.
    def test_invalid_date_rejected(self):
        invalid_dates = [
            "2026-11-23",
            datetime(2026, 11, 23, 12, 0),
            12345,
        ]

        for expense_date in invalid_dates:
            with self.subTest(expense_date=expense_date):
                with self.assertRaises(ValidationError):
                    create_expense(
                        **self.expense_data(
                            expense_date=expense_date
                        )
                    )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 5: Cross-hospital category is rejected.
    def test_cross_hospital_category_rejected(self):
        other_category = ExpenseCategory.objects.create(
            hospital_id=self.other_hospital_id,
            name="Other Utilities",
        )

        with self.assertRaises(
            ExpenseCategory.DoesNotExist
        ):
            create_expense(
                **self.expense_data(
                    expense_category_id=other_category.id
                )
            )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 6: Cross-hospital account is rejected.
    def test_cross_hospital_account_rejected(self):
        other_account = Account.objects.create(
            hospital_id=self.other_hospital_id,
            name="Other Hospital Cash",
            account_type=self.account_type,
            account_number="EXP-OTHER-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        with self.assertRaises(Account.DoesNotExist):
            create_expense(
                **self.expense_data(
                    account_id=other_account.id
                )
            )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 7: Inactive account is rejected.
    def test_inactive_account_rejected(self):
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        with self.assertRaises(Account.DoesNotExist):
            create_expense(
                **self.expense_data()
            )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 8: Explicit date and supplier ID are saved.
    def test_custom_date_and_supplier(self):
        supplier_id = uuid.uuid4()
        expense_date = date(2026, 11, 1)

        expense = create_expense(
            **self.expense_data(
                expense_date=expense_date,
                supplier_id=supplier_id,
            )
        )

        self.assertEqual(
            expense.expense_date,
            expense_date,
        )
        self.assertEqual(
            expense.supplier_id,
            supplier_id,
        )
        self.assertEqual(expense.status, "draft")
        self.assertEqual(Transaction.objects.count(), 0)