
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from apps.accounting.services import pay_expense

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.accounting.services import (
    create_expense,
    submit_expense_for_approval,
    approve_expense,
    reject_expense,
)
from apps.accounting.models import (
    Account,
    Expense,
    ExpenseCategory,
    Transaction,
)
from apps.accounting.services import (
    create_expense,
    submit_expense_for_approval,
)


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

    # 9. Draft expense can be submitted for approval.
    def test_submit_expense_success(self):
        expense = create_expense(**self.expense_data())

        result = submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        expense.refresh_from_db()

        self.assertEqual(
            expense.status,
            "pending_approval",
        )
        self.assertEqual(result.id, expense.id)
        self.assertIsNone(
            expense.approved_by_hospital_user_id
        )

        # Submission must not create a ledger entry.
        self.assertEqual(Transaction.objects.count(), 0)

    # 10. An already submitted expense cannot be resubmitted.
    def test_resubmission_rejected(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        with self.assertRaises(ValidationError):
            submit_expense_for_approval(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
            )

        self.assertEqual(Transaction.objects.count(), 0)

    # 11. Other expense statuses cannot be submitted.
    def test_non_draft_expense_rejected(self):
        expense = create_expense(**self.expense_data())

        for status in [
            "pending_approval",
            "approved",
            "paid",
            "rejected",
        ]:
            with self.subTest(status=status):
                expense.status = status
                expense.save(update_fields=["status"])

                with self.assertRaises(ValidationError):
                    submit_expense_for_approval(
                        expense_id=expense.id,
                        hospital_id=self.hospital_id,
                    )

                expense.refresh_from_db()
                self.assertEqual(expense.status, status)

    # 12. Another hospital cannot submit the expense.
    def test_cross_hospital_submission_rejected(self):
        expense = create_expense(**self.expense_data())

        with self.assertRaises(Expense.DoesNotExist):
            submit_expense_for_approval(
                expense_id=expense.id,
                hospital_id=self.other_hospital_id,
            )

        expense.refresh_from_db()
        self.assertEqual(expense.status, "draft")

    # 13. Expense with inactive account cannot be submitted.
    def test_inactive_account_submission_rejected(self):
        expense = create_expense(**self.expense_data())

        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            submit_expense_for_approval(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "draft")
        self.assertEqual(Transaction.objects.count(), 0)

    # 14. Pending expense can be approved.
    def test_approve_expense_success(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        approver_id = uuid.uuid4()

        approve_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
            approved_by_hospital_user_id=approver_id,
        )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "approved")
        self.assertEqual(
            expense.approved_by_hospital_user_id,
            approver_id,
        )
        self.assertEqual(Transaction.objects.count(), 0)

    # 15. Pending expense can be rejected.
    def test_reject_expense_success(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        reject_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "rejected")
        self.assertIsNone(
            expense.approved_by_hospital_user_id
        )
        self.assertEqual(Transaction.objects.count(), 0)

    # 16. Non-pending expenses cannot be approved.
    def test_approve_invalid_status_rejected(self):
        expense = create_expense(**self.expense_data())

        for status in [
            "draft",
            "approved",
            "paid",
            "rejected",
        ]:
            with self.subTest(status=status):
                expense.status = status
                expense.save(update_fields=["status"])

                with self.assertRaises(ValidationError):
                    approve_expense(
                        expense_id=expense.id,
                        hospital_id=self.hospital_id,
                        approved_by_hospital_user_id=uuid.uuid4(),
                    )

                expense.refresh_from_db()
                self.assertEqual(expense.status, status)

    # 17. Non-pending expenses cannot be rejected.
    def test_reject_invalid_status_rejected(self):
        expense = create_expense(**self.expense_data())

        for status in [
            "draft",
            "approved",
            "paid",
            "rejected",
        ]:
            with self.subTest(status=status):
                expense.status = status
                expense.save(update_fields=["status"])

                with self.assertRaises(ValidationError):
                    reject_expense(
                        expense_id=expense.id,
                        hospital_id=self.hospital_id,
                    )

                expense.refresh_from_db()
                self.assertEqual(expense.status, status)

    # 18. Invalid approver ID is rejected.
    def test_invalid_approver_rejected(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        for approver_id in [None, "invalid-uuid", ""]:
            with self.subTest(approver_id=approver_id):
                with self.assertRaises(ValidationError):
                    approve_expense(
                        expense_id=expense.id,
                        hospital_id=self.hospital_id,
                        approved_by_hospital_user_id=approver_id,
                    )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "pending_approval")
        self.assertIsNone(
            expense.approved_by_hospital_user_id
        )

    # 19. Another hospital cannot approve or reject.
    def test_cross_hospital_approval_rejected(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        with self.assertRaises(Expense.DoesNotExist):
            approve_expense(
                expense_id=expense.id,
                hospital_id=self.other_hospital_id,
                approved_by_hospital_user_id=uuid.uuid4(),
            )

        with self.assertRaises(Expense.DoesNotExist):
            reject_expense(
                expense_id=expense.id,
                hospital_id=self.other_hospital_id,
            )

        expense.refresh_from_db()
        self.assertEqual(expense.status, "pending_approval")

    # 20. Inactive account blocks approval.
    def test_inactive_account_approval_rejected(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            approve_expense(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
                approved_by_hospital_user_id=uuid.uuid4(),
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "pending_approval")
        self.assertEqual(Transaction.objects.count(), 0)

    # 21. Empty description blocks approval.
    def test_empty_description_approval_rejected(self):
        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        expense.description = "   "
        expense.save(update_fields=["description"])

        with self.assertRaises(ValidationError):
            approve_expense(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
                approved_by_hospital_user_id=uuid.uuid4(),
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "pending_approval")
        self.assertEqual(Transaction.objects.count(), 0)

    # ========================================================
    # EXPENSE PAYMENT TESTS
    # ========================================================

    def _create_approved_expense(self):
        """Prepare an approved expense for payment tests."""

        expense = create_expense(**self.expense_data())

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        approve_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
            approved_by_hospital_user_id=uuid.uuid4(),
        )

        return expense

    # 22. Approved expense can be paid.
    def test_pay_expense_success(self):
        expense = self._create_approved_expense()

        ledger = pay_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "paid")
        self.assertEqual(
            ledger.transaction_type,
            "expense",
        )
        self.assertEqual(
            ledger.amount,
            Decimal("5000.00"),
        )
        self.assertEqual(
            ledger.expense_id,
            expense.id,
        )
        self.assertEqual(
            ledger.account_id,
            self.account.id,
        )
        self.assertEqual(
            ledger.expense_category_id,
            self.category.id,
        )
        self.assertEqual(
            ledger.hospital_id,
            self.hospital_id,
        )
        self.assertEqual(Transaction.objects.count(), 1)

    # 23. Only approved expenses can be paid.
    def test_pay_invalid_status_rejected(self):
        expense = create_expense(**self.expense_data())

        for status in [
            "draft",
            "pending_approval",
            "rejected",
        ]:
            with self.subTest(status=status):
                expense.status = status
                expense.save(update_fields=["status"])

                with self.assertRaises(ValidationError):
                    pay_expense(
                        expense_id=expense.id,
                        hospital_id=self.hospital_id,
                    )

        self.assertEqual(Transaction.objects.count(), 0)

    # 24. Missing approval information blocks payment.
    def test_pay_without_approver_rejected(self):
        expense = self._create_approved_expense()

        expense.approved_by_hospital_user_id = None
        expense.save(
            update_fields=["approved_by_hospital_user_id"]
        )

        with self.assertRaises(ValidationError):
            pay_expense(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "approved")
        self.assertEqual(Transaction.objects.count(), 0)

    # 25. Same expense cannot be paid twice.
    def test_double_payment_rejected(self):
        expense = self._create_approved_expense()

        pay_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        with self.assertRaises(ValidationError):
            pay_expense(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
            )

        self.assertEqual(Transaction.objects.count(), 1)

    # 26. Existing ledger entry blocks duplicate payment.
    def test_existing_ledger_rejected(self):
        expense = self._create_approved_expense()

        Transaction.objects.create(
            hospital_id=self.hospital_id,
            account=self.account,
            expense_category=self.category,
            expense=expense,
            transaction_type="expense",
            amount=expense.amount,
            transaction_date=timezone.localdate(),
            description="Existing expense ledger",
        )

        with self.assertRaises(ValidationError):
            pay_expense(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "approved")
        self.assertEqual(Transaction.objects.count(), 1)

    # 27. Inactive account blocks expense payment.
    def test_inactive_account_payment_rejected(self):
        expense = self._create_approved_expense()

        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        with self.assertRaises(Account.DoesNotExist):
            pay_expense(
                expense_id=expense.id,
                hospital_id=self.hospital_id,
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "approved")
        self.assertEqual(Transaction.objects.count(), 0)

    # 28. Cross-hospital payment must be rejected.
    def test_cross_hospital_payment_rejected(self):
        expense = self._create_approved_expense()

        with self.assertRaises(Expense.DoesNotExist):
            pay_expense(
                expense_id=expense.id,
                hospital_id=self.other_hospital_id,
            )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "approved")
        self.assertEqual(Transaction.objects.count(), 0)

    # 29. Ledger failure rolls back payment status.
    def test_expense_ledger_failure_rolls_back(self):
        expense = self._create_approved_expense()

        with patch(
            "apps.accounting.services.Transaction.objects.create",
            side_effect=RuntimeError(
                "Simulated expense ledger failure"
            ),
        ):
            with self.assertRaises(RuntimeError):
                pay_expense(
                    expense_id=expense.id,
                    hospital_id=self.hospital_id,
                )

        expense.refresh_from_db()

        self.assertEqual(expense.status, "approved")
        self.assertEqual(Transaction.objects.count(), 0)
