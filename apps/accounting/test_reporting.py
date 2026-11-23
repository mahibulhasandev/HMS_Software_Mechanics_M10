
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account,
    ExpenseCategory,
    Invoice,
    Transaction,
)
from apps.accounting.services import (
    process_payment,
    process_refund,
    create_expense,
    submit_expense_for_approval,
    approve_expense,
    pay_expense,
)
from apps.accounting.reporting import (
    get_cash_flow_summary,
    get_account_wise_summary,
)


class FinancialReportingTests(TestCase):

    def setUp(self):
        self.hospital_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.today = timezone.localdate()

        account_type = list(
            Account._meta.get_field(
                "account_type"
            ).flatchoices
        )[0][0]

        self.account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Main Cash Account",
            account_type=account_type,
            account_number="REPORT-ACC-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        self.category = ExpenseCategory.objects.create(
            hospital_id=self.hospital_id,
            name="Utilities",
        )

        self.invoice = Invoice.objects.create(
            hospital_id=self.hospital_id,
            created_by_hospital_user_id=self.user_id,
            invoice_number="REPORT-INV-001",
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

    def report(self, **overrides):
        data = {
            "hospital_id": self.hospital_id,
            "start_date": self.today,
            "end_date": self.today,
        }
        data.update(overrides)
        return get_cash_flow_summary(**data)

    def receive_payment(self, amount="1000.00"):
        return process_payment(
            payment_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            invoice_id=self.invoice.id,
            account_id=self.account.id,
            received_by_hospital_user_id=self.user_id,
            amount=amount,
            method="cash",
            reference_no=str(uuid.uuid4()),
        )

    def record_expense(self, amount="300.00"):
        expense = create_expense(
            hospital_id=self.hospital_id,
            expense_category_id=self.category.id,
            account_id=self.account.id,
            amount=amount,
            description="Electricity Bill",
        )

        submit_expense_for_approval(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

        approve_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
            approved_by_hospital_user_id=self.user_id,
        )

        return pay_expense(
            expense_id=expense.id,
            hospital_id=self.hospital_id,
        )

    # 1. Empty ledger should return zero totals.
    def test_empty_report(self):
        result = self.report()

        self.assertEqual(
            result["total_income"],
            Decimal("0.00"),
        )
        self.assertEqual(
            result["total_expenses"],
            Decimal("0.00"),
        )
        self.assertEqual(
            result["total_refunds"],
            Decimal("0.00"),
        )
        self.assertEqual(
            result["net_cash_flow"],
            Decimal("0.00"),
        )

    # 2. Income, expense and refund calculation.
    def test_cash_flow_calculation(self):
        payment = self.receive_payment("1000.00")

        process_refund(
            refund_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            original_payment_id=payment.id,
            received_by_hospital_user_id=self.user_id,
            amount="200.00",
            method="cash",
            reference_no="REPORT-REFUND-001",
        )

        self.record_expense("300.00")

        result = self.report()

        self.assertEqual(
            result["total_income"],
            Decimal("1000.00"),
        )
        self.assertEqual(
            result["total_expenses"],
            Decimal("300.00"),
        )
        self.assertEqual(
            result["total_refunds"],
            Decimal("200.00"),
        )
        self.assertEqual(
            result["net_cash_flow"],
            Decimal("500.00"),
        )

        # Reporting must not modify the ledger.
        self.assertEqual(
            Transaction.objects.count(),
            3,
        )

    # 3. Reports must respect inclusive date ranges.
    def test_date_range_filtering(self):
        self.receive_payment("500.00")

        today_report = self.report()

        self.assertEqual(
            today_report["total_income"],
            Decimal("500.00"),
        )

        tomorrow = self.today + timedelta(days=1)

        future_report = self.report(
            start_date=tomorrow,
            end_date=tomorrow,
        )

        self.assertEqual(
            future_report["total_income"],
            Decimal("0.00"),
        )

    # 4. Other hospitals' transactions are excluded.
    def test_hospital_isolation(self):
        self.receive_payment("400.00")

        other_hospital_id = uuid.uuid4()

        other_account = Account.objects.create(
            hospital_id=other_hospital_id,
            name="Other Hospital Cash",
            account_type=self.account.account_type,
            account_number="REPORT-OTHER-ACC",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        other_invoice = Invoice.objects.create(
            hospital_id=other_hospital_id,
            created_by_hospital_user_id=uuid.uuid4(),
            invoice_number="REPORT-OTHER-INV",
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

        process_payment(
            payment_id=uuid.uuid4(),
            hospital_id=other_hospital_id,
            invoice_id=other_invoice.id,
            account_id=other_account.id,
            received_by_hospital_user_id=uuid.uuid4(),
            amount="700.00",
            method="cash",
            reference_no="OTHER-HOSPITAL-PAY",
        )

        result = self.report()

        self.assertEqual(
            result["total_income"],
            Decimal("400.00"),
        )

        other_result = self.report(
            hospital_id=other_hospital_id,
        )

        self.assertEqual(
            other_result["total_income"],
            Decimal("700.00"),
        )

    # 5. Invalid dates must be rejected.
    def test_invalid_dates_rejected(self):
        invalid_ranges = [
            {
                "start_date": "2026-11-23",
            },
            {
                "end_date": datetime(2026, 11, 23, 12, 0),
            },
            {
                "start_date": self.today + timedelta(days=1),
                "end_date": self.today,
            },
        ]

        for values in invalid_ranges:
            with self.subTest(values=values):
                with self.assertRaises(ValidationError):
                    self.report(**values)

    # 6. Reversal must not be silently ignored.
    def test_reversal_rejected(self):
        payment = self.receive_payment("500.00")

        original_ledger = Transaction.objects.get(
            payment=payment,
        )

        Transaction.objects.create(
            hospital_id=self.hospital_id,
            account=self.account,
            reversed_transaction=original_ledger,
            transaction_type="reversal",
            amount=Decimal("100.00"),
            transaction_date=self.today,
            description="Test reversal",
        )

        with self.assertRaises(ValidationError):
            self.report()

    # ========================================================
    # ACCOUNT-WISE REPORTING TESTS
    # ========================================================

    def account_report(self, **overrides):
        data = {
            "hospital_id": self.hospital_id,
            "start_date": self.today,
            "end_date": self.today,
        }
        data.update(overrides)
        return get_account_wise_summary(**data)

    def test_account_wise_empty_report(self):
        result = self.account_report()

        self.assertEqual(result["accounts"], [])
        self.assertEqual(
            result["overall"]["net_cash_flow"],
            Decimal("0.00"),
        )

    def test_account_wise_cash_flow(self):
        payment = self.receive_payment("1000.00")

        process_refund(
            refund_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            original_payment_id=payment.id,
            received_by_hospital_user_id=self.user_id,
            amount="200.00",
            method="cash",
            reference_no="ACCOUNT-REFUND-001",
        )

        self.record_expense("300.00")

        result = self.account_report()

        self.assertEqual(len(result["accounts"]), 1)

        account_data = result["accounts"][0]

        self.assertEqual(
            account_data["account_id"],
            self.account.id,
        )
        self.assertEqual(
            account_data["total_income"],
            Decimal("1000.00"),
        )
        self.assertEqual(
            account_data["total_expenses"],
            Decimal("300.00"),
        )
        self.assertEqual(
            account_data["total_refunds"],
            Decimal("200.00"),
        )
        self.assertEqual(
            account_data["net_cash_flow"],
            Decimal("500.00"),
        )
        self.assertEqual(
            result["overall"]["net_cash_flow"],
            Decimal("500.00"),
        )

    def test_multiple_accounts_summary(self):
        self.receive_payment("400.00")

        bank_account = Account.objects.create(
            hospital_id=self.hospital_id,
            name="Bank Account",
            account_type=self.account.account_type,
            account_number="REPORT-BANK-001",
            opening_balance=Decimal("0.00"),
            is_active=True,
        )

        process_payment(
            payment_id=uuid.uuid4(),
            hospital_id=self.hospital_id,
            invoice_id=self.invoice.id,
            account_id=bank_account.id,
            received_by_hospital_user_id=self.user_id,
            amount="600.00",
            method="bank_transfer",
            reference_no="REPORT-BANK-PAY-001",
        )

        self.record_expense("200.00")

        result = self.account_report()

        self.assertEqual(len(result["accounts"]), 2)

        accounts = {
            row["account_id"]: row
            for row in result["accounts"]
        }

        self.assertEqual(
            accounts[self.account.id]["net_cash_flow"],
            Decimal("200.00"),
        )
        self.assertEqual(
            accounts[bank_account.id]["net_cash_flow"],
            Decimal("600.00"),
        )
        self.assertEqual(
            result["overall"]["net_cash_flow"],
            Decimal("800.00"),
        )

    def test_account_wise_filters(self):
        self.receive_payment("500.00")

        other_hospital = uuid.uuid4()

        other_result = self.account_report(
            hospital_id=other_hospital,
        )

        self.assertEqual(other_result["accounts"], [])

        tomorrow = self.today + timedelta(days=1)

        future_result = self.account_report(
            start_date=tomorrow,
            end_date=tomorrow,
        )

        self.assertEqual(future_result["accounts"], [])
        self.assertEqual(
            future_result["overall"]["total_income"],
            Decimal("0.00"),
        )

    def test_account_wise_reversal_rejected(self):
        payment = self.receive_payment("500.00")

        original_ledger = Transaction.objects.get(
            payment=payment,
        )

        Transaction.objects.create(
            hospital_id=self.hospital_id,
            account=self.account,
            reversed_transaction=original_ledger,
            transaction_type="reversal",
            amount=Decimal("100.00"),
            transaction_date=self.today,
            description="Test account reversal",
        )

        with self.assertRaises(ValidationError):
            self.account_report()