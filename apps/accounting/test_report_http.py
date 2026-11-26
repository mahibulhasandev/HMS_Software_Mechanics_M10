from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.test import TestCase

from apps.accounting.models import Expense, Transaction
from apps.accounting import test_transaction_http

from apps.accounting._test_integrity_helpers import allow_invalid_reversal_fixture


class FinancialReportHTTPTests(TestCase):

    URL = "/api/accounting/reports/financial-summary/"

    @classmethod
    def setUpTestData(cls):

        test_transaction_http.TransactionHTTPTests.setUpTestData.__func__(cls)

    def params(self, **overrides):

        data = {
            "date_from": self.old_date.isoformat(),
            "date_to": self.today.isoformat(),
        }

        data.update(overrides)

        return data

    def get_report(self, user=None, **overrides):

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

    def assert_totals(self, data, **expected):

        for field, value in expected.items():

            with self.subTest(field=field):

                self.assertEqual(
                    data[field],
                    value,
                )

    def add_reversal(self, original, amount=None):

        return Transaction.objects.create(
            hospital_id=original.hospital_id,
            account_id=original.account_id,
            income_category_id=original.income_category_id,
            expense_category_id=original.expense_category_id,
            reversed_transaction=original,
            transaction_type="reversal",
            amount=(
                original.amount
                if amount is None
                else Decimal(amount)
            ),
            transaction_date=self.today,
            description="Report reversal test fixture",
        )

    # Test 1
    def test_financial_summary(self):

        data = self.get_report()

        self.assertEqual(
            data["hospital_id"],
            str(self.hospital_a.pk),
        )

        self.assertEqual(
            data["group_by"],
            "summary",
        )

        self.assertEqual(
            data["breakdown"],
            [],
        )

        self.assert_totals(
            data["summary"],
            income="1000.00",
            expense="300.00",
            refund="200.00",
            reversal_inflow="300.00",
            reversal_outflow="0.00",
            total_inflow="1300.00",
            total_outflow="500.00",
            net_movement="800.00",
            transaction_count=4,
        )

    # Test 2
    def test_date_grouping(self):

        data = self.get_report(
            group_by="date"
        )

        rows = {
            row["date"]: row
            for row in data["breakdown"]
        }

        self.assertEqual(len(rows), 2)

        self.assert_totals(
            rows[self.old_date.isoformat()],
            income="0.00",
            expense="300.00",
            net_movement="-300.00",
            transaction_count=1,
        )

        self.assert_totals(
            rows[self.today.isoformat()],
            income="1000.00",
            refund="200.00",
            reversal_inflow="300.00",
            net_movement="1100.00",
            transaction_count=3,
        )

        self.assertEqual(
            data["summary"],
            self.get_report()["summary"],
        )

    # Test 3
    def test_category_grouping(self):

        data = self.get_report(
            group_by="category"
        )

        rows = [
            row
            for row in data["breakdown"]
            if row["expense_category_id"] == str(
                self.category_a.pk
            )
        ]

        self.assertEqual(len(rows), 1)

        self.assert_totals(
            rows[0],
            expense="300.00",
            reversal_inflow="300.00",
            net_movement="0.00",
            transaction_count=2,
        )

        self.assertEqual(
            data["summary"],
            self.get_report()["summary"],
        )

        for field in (
            "income",
            "expense",
            "refund",
            "reversal_inflow",
            "reversal_outflow",
            "total_inflow",
            "total_outflow",
            "net_movement",
        ):

            total = sum(
                Decimal(row[field])
                for row in data["breakdown"]
            )

            self.assertEqual(
                total,
                Decimal(data["summary"][field]),
            )

    # Test 4
    def test_account_filter(self):

        data = self.get_report(
            account_id=str(self.account_a.pk)
        )

        self.assert_totals(
            data["summary"],
            income="1000.00",
            expense="0.00",
            refund="200.00",
            net_movement="800.00",
            transaction_count=2,
        )

        data = self.get_report(
            account_id=str(self.account_a2.pk)
        )

        self.assert_totals(
            data["summary"],
            income="0.00",
            expense="300.00",
            refund="0.00",
            reversal_inflow="300.00",
            net_movement="0.00",
            transaction_count=2,
        )

    # Test 5
    def test_date_range_boundaries(self):

        data = self.get_report(
            date_from=self.old_date.isoformat(),
            date_to=self.old_date.isoformat(),
        )

        self.assert_totals(
            data["summary"],
            expense="300.00",
            net_movement="-300.00",
            transaction_count=1,
        )

        data = self.get_report(
            date_from=self.today.isoformat(),
            date_to=self.today.isoformat(),
        )

        self.assert_totals(
            data["summary"],
            net_movement="1100.00",
            transaction_count=3,
        )

    # Test 6
    def test_empty_report(self):

        future = (
            self.today + timedelta(days=30)
        ).isoformat()

        for group in (
            "summary",
            "date",
            "category",
        ):

            data = self.get_report(
                date_from=future,
                date_to=future,
                group_by=group,
            )

            self.assertEqual(
                data["breakdown"],
                [],
            )

            self.assert_totals(
                data["summary"],
                income="0.00",
                expense="0.00",
                refund="0.00",
                reversal_inflow="0.00",
                reversal_outflow="0.00",
                total_inflow="0.00",
                total_outflow="0.00",
                net_movement="0.00",
                transaction_count=0,
            )

    # Test 7
    def test_invalid_filters_rejected(self):

        self.client.force_login(self.user_a)

        invalid_params = (
            {},
            {"date_from": self.today.isoformat()},
            {"date_to": self.today.isoformat()},
            self.params(date_from="invalid-date"),
            self.params(date_to="2026-02-30"),
            self.params(group_by="invalid"),
            self.params(account_id="invalid-uuid"),
            self.params(
                date_from="2026-12-31",
                date_to="2026-01-01",
            ),
        )

        for params in invalid_params:

            with self.subTest(params=params):

                response = self.client.get(
                    self.URL,
                    params,
                )

                self.assertEqual(
                    response.status_code,
                    400,
                    response.content,
                )

    # Test 8
    def test_maximum_report_period(self):

        self.client.force_login(self.user_a)

        start = self.today - timedelta(days=365)

        response = self.client.get(
            self.URL,
            self.params(
                date_from=start.isoformat()
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
            response.content,
        )

        start = self.today - timedelta(days=366)

        response = self.client.get(
            self.URL,
            self.params(
                date_from=start.isoformat()
            ),
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    # Test 9
    def test_cross_hospital_isolation(self):

        self.client.force_login(self.user_a)

        for group in (
            "summary",
            "date",
            "category",
        ):

            response = self.client.get(
                self.URL,
                self.params(
                    group_by=group,
                    hospital_id=str(self.hospital_b.pk),
                ),
                HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
            )

            self.assertEqual(response.status_code, 200)

            data = response.json()

            self.assertEqual(
                data["hospital_id"],
                str(self.hospital_a.pk),
            )

            self.assert_totals(
                data["summary"],
                net_movement="800.00",
                transaction_count=4,
            )

        data = self.get_report(
            account_id=str(self.account_b.pk)
        )

        self.assert_totals(
            data["summary"],
            net_movement="0.00",
            transaction_count=0,
        )

        data = self.get_report(
            user=self.user_b
        )

        self.assertEqual(
            data["hospital_id"],
            str(self.hospital_b.pk),
        )

        self.assert_totals(
            data["summary"],
            expense="400.00",
            net_movement="-400.00",
            transaction_count=1,
        )

    # Test 10
    def test_role_based_read_access(self):

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            with self.subTest(user=user.username):

                data = self.get_report(
                    user=user
                )

                self.assert_totals(
                    data["summary"],
                    net_movement="800.00",
                    transaction_count=4,
                )

    # Test 11
    def test_unauthorized_access(self):

        self.client.logout()

        response = self.client.get(
            self.URL,
            self.params(),
        )

        self.assertEqual(
            response.status_code,
            401,
        )

        self.client.force_login(
            self.no_membership
        )

        response = self.client.get(
            self.URL,
            self.params(),
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    # Test 12
    def test_report_write_operations_blocked(self):

        before = list(
            Transaction.objects.order_by("pk").values()
        )

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            self.client.force_login(user)

            for method in (
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
            ):

                with self.subTest(
                    user=user.username,
                    method=method,
                ):

                    response = self.client.generic(
                        method,
                        self.URL,
                        data='{"income":"99999.00"}',
                        content_type="application/json",
                    )

                    self.assertIn(
                        response.status_code,
                        (403, 405),
                        response.content,
                    )

        self.assertEqual(
            before,
            list(
                Transaction.objects.order_by("pk").values()
            ),
        )

    # Test 13
    def test_invalid_reversal_rejected(self):

        with allow_invalid_reversal_fixture():
            self.add_reversal(
                self.income,
                amount="999.00",
            )

        self.client.force_login(self.user_a)

        for group in (
            "summary",
            "date",
            "category",
        ):

            response = self.client.get(
                self.URL,
                self.params(group_by=group),
            )

            self.assertEqual(
                response.status_code,
                409,
                response.content,
            )

    # Test 14
    def test_reversal_direction(self):

        self.add_reversal(self.income)

        data = self.get_report()

        self.assert_totals(
            data["summary"],
            reversal_outflow="1000.00",
            total_inflow="1300.00",
            total_outflow="1500.00",
            net_movement="-200.00",
            transaction_count=5,
        )

        self.add_reversal(self.refund)

        data = self.get_report()

        self.assert_totals(
            data["summary"],
            reversal_inflow="500.00",
            reversal_outflow="1000.00",
            total_inflow="1500.00",
            total_outflow="1500.00",
            net_movement="0.00",
            transaction_count=6,
        )

    # Test 15
    def test_unposted_expenses_excluded(self):

        for status in (
            "draft",
            "pending_approval",
            "approved",
            "rejected",
        ):

            Expense.objects.create(
                hospital_id=self.hospital_a.pk,
                expense_category=self.category_a,
                account=self.account_a,
                amount=Decimal("500.00"),
                expense_date=self.today,
                description=f"Unposted expense: {status}",
                status=status,
                approved_by_hospital_user_id=(
                    self.approver
                    if status == "approved"
                    else None
                ),
            )

        data = self.get_report()

        self.assert_totals(
            data["summary"],
            expense="300.00",
            net_movement="800.00",
            transaction_count=4,
        )
