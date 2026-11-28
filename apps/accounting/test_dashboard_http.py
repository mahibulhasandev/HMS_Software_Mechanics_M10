from apps.accounting._test_helpers import create_test_user
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account,
    AccountingMembership,
    Invoice,
    Expense,
    Transaction,
)

from apps.accounting import test_transaction_http
from apps.hospitals.models import Hospital

from apps.accounting._test_integrity_helpers import allow_invalid_reversal_fixture


class DashboardHTTPTests(TestCase):

    URL = "/api/accounting/dashboard/"

    @classmethod
    def setUpTestData(cls):

        test_transaction_http.TransactionHTTPTests.setUpTestData.__func__(cls)

        with connection.cursor() as cursor:

            cursor.execute(
                "GRANT SELECT ON accounts, invoices, expenses, "
                "transactions TO hms_app"
            )

        # Additional invoice fixtures.

        for status, total, paid in (
            ("issued", "900.00", "0.00"),
            ("partially_paid", "800.00", "300.00"),
            ("draft", "500.00", "0.00"),
            ("paid", "500.00", "500.00"),
            ("voided", "500.00", "0.00"),
        ):

            Invoice.objects.create(
                hospital_id=cls.hospital_a.pk,
                created_by_hospital_user_id=cls.actor,
                invoice_number=f"DASH-INV-{status}",
                subtotal=Decimal(total),
                discount=Decimal("0.00"),
                total=Decimal(total),
                amount_paid=Decimal(paid),
                status=status,
                issued_at=timezone.now(),
            )

        # Another hospital's outstanding invoice.

        Invoice.objects.create(
            hospital_id=cls.hospital_b.pk,
            created_by_hospital_user_id=(
                AccountingMembership.objects.get(
                    user=cls.user_b
                ).actor_uuid
            ),
            invoice_number="DASH-INV-B",
            subtotal=Decimal("800.00"),
            discount=Decimal("0.00"),
            total=Decimal("800.00"),
            amount_paid=Decimal("0.00"),
            status="issued",
            issued_at=timezone.now(),
        )

        # Additional expense fixtures.

        for status, amount in (
            ("pending_approval", "300.00"),
            ("pending_approval", "400.00"),
            ("approved", "450.00"),
            ("draft", "500.00"),
            ("rejected", "600.00"),
        ):

            Expense.objects.create(
                hospital_id=cls.hospital_a.pk,
                expense_category=cls.category_a,
                account=cls.account_a,
                amount=Decimal(amount),
                expense_date=cls.today,
                description=f"Dashboard expense {status}",
                status=status,
                approved_by_hospital_user_id=(
                    cls.approver
                    if status == "approved"
                    else None
                ),
            )

        Expense.objects.create(
            hospital_id=cls.hospital_b.pk,
            expense_category=cls.category_b,
            account=cls.account_b,
            amount=Decimal("999.00"),
            expense_date=cls.today,
            description="Hospital B pending expense",
            status="pending_approval",
        )

    def params(self, **overrides):

        data = {
            "date_from": self.old_date.isoformat(),
            "date_to": self.today.isoformat(),
        }

        data.update(overrides)

        return data

    def get_dashboard(self, user=None, **overrides):

        self.client.force_login(
            user or self.user_a
        )

        response = self.client.get(
            self.URL,
            self.params(**overrides),
        )

        self.assertEqual(
            response.status_code,
            200,
            response.content,
        )

        return response.json()

    # Test 1
    def test_account_summary(self):

        data = self.get_dashboard()["account_summary"]

        self.assertEqual(data["account_count"], 2)

        self.assertEqual(
            data["total_opening_balance"], "15000.00"
        )

        self.assertEqual(
            data["total_net_movement"], "800.00"
        )

        self.assertEqual(
            data["total_current_balance"], "15800.00"
        )

        accounts = {
            row["id"]: row
            for row in data["accounts"]
        }

        self.assertEqual(
            accounts[str(self.account_a.pk)]["current_balance"],
            "10800.00",
        )

        self.assertEqual(
            accounts[str(self.account_a2.pk)]["current_balance"],
            "5000.00",
        )

        self.assertFalse(data["has_more_accounts"])

    # Test 2
    def test_outstanding_invoice_summary(self):

        data = self.get_dashboard()["invoice_summary"]

        self.assertEqual(
            data["outstanding_invoice_count"], 3
        )

        self.assertEqual(
            data["outstanding_amount"], "1600.00"
        )

    # Test 3
    def test_expense_approval_summary(self):

        data = self.get_dashboard()["expense_summary"]

        self.assertEqual(
            data["pending_approval_count"], 2
        )

        self.assertEqual(
            data["pending_approval_amount"], "700.00"
        )

        self.assertEqual(
            data["approved_unpaid_count"], 1
        )

        self.assertEqual(
            data["approved_unpaid_amount"], "450.00"
        )

    # Test 4
    def test_financial_summary_reconciliation(self):

        dashboard = self.get_dashboard()

        financial = dashboard["financial_summary"]

        summary = financial["summary"]

        expected = {
            "income": "1000.00",
            "expense": "300.00",
            "refund": "200.00",
            "reversal_inflow": "300.00",
            "reversal_outflow": "0.00",
            "total_inflow": "1300.00",
            "total_outflow": "500.00",
            "net_movement": "800.00",
            "transaction_count": 4,
        }

        self.assertEqual(summary, expected)

        response = self.client.get(
            "/api/accounting/reports/financial-summary/",
            self.params(),
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            summary,
            response.json()["summary"],
        )

        daily = financial["daily_movement"]

        self.assertEqual(len(daily), 2)

        self.assertEqual(
            sum(
                Decimal(row["net_movement"])
                for row in daily
            ),
            Decimal("800.00"),
        )

        recent = financial["recent_transactions"]

        self.assertEqual(len(recent), 4)

        self.assertEqual(
            {row["id"] for row in recent},
            {
                str(self.income.pk),
                str(self.refund.pk),
                str(self.expense.pk),
                str(self.reversal.pk),
            },
        )

    # Test 5
    def test_period_filter_and_current_totals(self):

        data = self.get_dashboard(
            date_from=self.old_date.isoformat(),
            date_to=self.old_date.isoformat(),
        )

        financial = data["financial_summary"]

        self.assertEqual(
            financial["summary"]["net_movement"],
            "-300.00",
        )

        self.assertEqual(
            len(financial["recent_transactions"]), 1
        )

        # Current account and invoice balances are not
        # restricted to the selected financial period.

        self.assertEqual(
            data["account_summary"]["total_current_balance"],
            "15800.00",
        )

        self.assertEqual(
            data["invoice_summary"]["outstanding_amount"],
            "1600.00",
        )

        future = (
            self.today + timedelta(days=30)
        ).isoformat()

        data = self.get_dashboard(
            date_from=future,
            date_to=future,
        )

        financial = data["financial_summary"]

        self.assertEqual(
            financial["summary"]["net_movement"],
            "0.00",
        )

        self.assertEqual(
            financial["summary"]["transaction_count"], 0
        )

        self.assertEqual(financial["daily_movement"], [])
        self.assertEqual(financial["recent_transactions"], [])

    # Test 6
    def test_cross_hospital_isolation(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            self.params(
                hospital_id=str(self.hospital_b.pk)
            ),
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        data = response.json()

        self.assertEqual(
            data["hospital_id"], str(self.hospital_a.pk)
        )

        self.assertEqual(
            data["account_summary"]["total_current_balance"],
            "15800.00",
        )

        self.assertEqual(
            data["invoice_summary"]["outstanding_amount"],
            "1600.00",
        )

        self.assertEqual(
            data["expense_summary"]["pending_approval_amount"],
            "700.00",
        )

        self.assertEqual(
            data["financial_summary"]["summary"]["net_movement"],
            "800.00",
        )

        data = self.get_dashboard(user=self.user_b)

        self.assertEqual(
            data["hospital_id"], str(self.hospital_b.pk)
        )

        self.assertEqual(
            data["account_summary"]["total_current_balance"],
            "9600.00",
        )

        self.assertEqual(
            data["invoice_summary"]["outstanding_amount"],
            "800.00",
        )

        self.assertEqual(
            data["expense_summary"]["pending_approval_amount"],
            "999.00",
        )

        self.assertEqual(
            data["financial_summary"]["summary"]["net_movement"],
            "-400.00",
        )

    # Test 7
    def test_role_based_access(self):

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            with self.subTest(user=user.email):

                data = self.get_dashboard(user=user)

                self.assertEqual(
                    data["account_summary"]["total_current_balance"],
                    "15800.00",
                )

        self.client.logout()

        response = self.client.get(
            self.URL, self.params()
        )

        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.no_membership)

        response = self.client.get(
            self.URL, self.params()
        )

        self.assertEqual(response.status_code, 403)

    # Test 8
    def test_invalid_date_filters(self):

        self.client.force_login(self.user_a)

        invalid = (
            {},
            {"date_from": self.today.isoformat()},
            {"date_to": self.today.isoformat()},
            self.params(date_from="invalid"),
            self.params(date_to="2026-02-30"),
            self.params(
                date_from="2026-12-31",
                date_to="2026-01-01",
            ),
            self.params(
                date_from=(
                    self.today - timedelta(days=366)
                ).isoformat()
            ),
        )

        for params in invalid:

            with self.subTest(params=params):

                response = self.client.get(
                    self.URL, params
                )

                self.assertEqual(
                    response.status_code,
                    400,
                    response.content,
                )

        response = self.client.get(
            self.URL,
            self.params(
                date_from=(
                    self.today - timedelta(days=365)
                ).isoformat()
            ),
        )

        self.assertEqual(response.status_code, 200)

    # Test 9
    def test_dashboard_preview_limits(self):

        Account.objects.bulk_create([
            Account(
                hospital_id=self.hospital_a.pk,
                name=f"Dashboard Account {i:02d}",
                account_type="cash",
                account_number=str(uuid4()),
                opening_balance=Decimal("100.00"),
                is_active=True,
            )
            for i in range(9)
        ])

        for i in range(7):

            expense = Expense.objects.create(
                hospital_id=self.hospital_a.pk,
                expense_category=self.category_a,
                account=self.account_a,
                amount=Decimal("10.00"),
                expense_date=self.today,
                description=f"Dashboard preview expense {i}",
                status="paid",
                approved_by_hospital_user_id=self.approver,
            )

            Transaction.objects.create(
                hospital_id=self.hospital_a.pk,
                account=self.account_a,
                expense_category=self.category_a,
                expense=expense,
                transaction_type="expense",
                amount=Decimal("10.00"),
                transaction_date=self.today,
                description=f"Dashboard preview ledger {i}",
            )

        data = self.get_dashboard()

        accounts = data["account_summary"]

        self.assertEqual(accounts["account_count"], 11)
        self.assertEqual(len(accounts["accounts"]), 10)
        self.assertTrue(accounts["has_more_accounts"])

        self.assertEqual(
            accounts["total_current_balance"],
            "16630.00",
        )

        financial = data["financial_summary"]

        self.assertEqual(
            financial["summary"]["transaction_count"], 11
        )

        self.assertEqual(
            financial["summary"]["net_movement"],
            "730.00",
        )

        recent = financial["recent_transactions"]

        self.assertEqual(len(recent), 10)

        expected = list(
            Transaction.objects.filter(
                hospital_id=self.hospital_a.pk,
                transaction_date__gte=self.old_date,
                transaction_date__lte=self.today,
            ).order_by(
                "-transaction_date", "-id"
            ).values_list("pk", flat=True)[:10]
        )

        self.assertEqual(
            [row["id"] for row in recent],
            [str(pk) for pk in expected],
        )

    # Test 10
    def test_dashboard_write_operations_blocked(self):

        models = (
            Account,
            Invoice,
            Expense,
            Transaction,
        )

        before = {
            model.__name__: list(
                model.objects.order_by("pk").values()
            )
            for model in models
        }

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            self.client.force_login(user)

            for method in (
                "POST", "PUT", "PATCH", "DELETE"
            ):

                with self.subTest(
                    user=user.email,
                    method=method,
                ):

                    response = self.client.generic(
                        method,
                        self.URL,
                        data='{"total_current_balance":"99999.00"}',
                        content_type="application/json",
                    )

                    self.assertIn(
                        response.status_code,
                        (403, 405),
                        response.content,
                    )

        after = {
            model.__name__: list(
                model.objects.order_by("pk").values()
            )
            for model in models
        }

        self.assertEqual(before, after)

    # Test 11
    def test_invalid_ledger_rejected(self):

        with allow_invalid_reversal_fixture():
            Transaction.objects.create(
                hospital_id=self.hospital_a.pk,
                account=self.account_a,
                reversed_transaction=self.income,
                transaction_type="reversal",
                amount=Decimal("999.00"),
                transaction_date=self.today,
                description="Invalid dashboard reversal fixture",
            )

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL, self.params()
        )

        self.assertEqual(
            response.status_code,
            409,
            response.content,
        )

    # Test 12
    def test_empty_hospital_dashboard(self):

        hospital = Hospital.objects.create(
            name="Empty Dashboard Hospital",
            registration_number="DASH-EMPTY",
            address="Test address",
            phone="100003",
            email="empty-dashboard@example.com",
            timezone="Asia/Dhaka",
        )

        user = create_test_user(

    email="empty_dashboard_user@example.test",
)

        AccountingMembership.objects.create(
            user=user,
            hospital=hospital,
            role="accountant",
            is_active=True,
        )

        data = self.get_dashboard(user=user)

        accounts = data["account_summary"]
        invoices = data["invoice_summary"]
        expenses = data["expense_summary"]
        financial = data["financial_summary"]

        self.assertEqual(accounts["account_count"], 0)
        self.assertEqual(accounts["accounts"], [])

        self.assertEqual(
            accounts["total_current_balance"], "0.00"
        )

        self.assertEqual(
            invoices["outstanding_amount"], "0.00"
        )

        self.assertEqual(
            expenses["pending_approval_amount"], "0.00"
        )

        self.assertEqual(
            expenses["approved_unpaid_amount"], "0.00"
        )

        self.assertEqual(
            financial["summary"]["transaction_count"], 0
        )

        self.assertEqual(
            financial["summary"]["net_movement"], "0.00"
        )

        self.assertEqual(financial["daily_movement"], [])
        self.assertEqual(financial["recent_transactions"], [])
