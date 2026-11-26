from decimal import Decimal
from uuid import uuid4

from django.db import connection
from django.test import TestCase

from apps.accounting.models import (
    Account,
    Expense,
    Transaction,
)

from apps.accounting import test_transaction_http


class BalanceHTTPTests(TestCase):

    URL = "/api/accounting/accounts/balances/"

    @classmethod
    def setUpTestData(cls):

        # Reuse the verified transaction test fixtures.

        test_transaction_http.TransactionHTTPTests.setUpTestData.__func__(cls)

        with connection.cursor() as cursor:

            cursor.execute(
                "GRANT SELECT ON accounts TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT ON transactions TO hms_app"
            )

    def detail_url(self, account):

        return (
            f"/api/accounting/accounts/"
            f"{account.pk}/balance/"
        )

    def get_balance(self, account, user=None):

        self.client.force_login(
            user or self.user_a
        )

        response = self.client.get(
            self.detail_url(account)
        )

        self.assertEqual(
            response.status_code,
            200,
            response.content,
        )

        return response.json()["account"]

    def assert_balance(
        self,
        data,
        opening,
        movement,
        current,
    ):

        self.assertEqual(
            data["opening_balance"],
            opening,
        )

        self.assertEqual(
            data["net_movement"],
            movement,
        )

        self.assertEqual(
            data["current_balance"],
            current,
        )

    def new_account(
        self,
        opening="0.00",
        active=True,
    ):

        return Account.objects.create(
            hospital_id=self.hospital_a.pk,
            name="Balance Test Account",
            account_type="cash",
            account_number=str(uuid4()),
            opening_balance=Decimal(opening),
            is_active=active,
        )

    def add_expense(self, account, amount):

        expense = Expense.objects.create(
            hospital_id=self.hospital_a.pk,
            expense_category=self.category_a,
            account=account,
            amount=Decimal(amount),
            expense_date=self.today,
            description="Balance test expense",
            status="paid",
            approved_by_hospital_user_id=self.approver,
        )

        return Transaction.objects.create(
            hospital_id=self.hospital_a.pk,
            account=account,
            expense_category=self.category_a,
            expense=expense,
            transaction_type="expense",
            amount=Decimal(amount),
            transaction_date=self.today,
            description="Balance test expense",
        )

    def add_reversal(
        self,
        original,
        amount=None,
        account=None,
    ):

        return Transaction.objects.create(
            hospital_id=original.hospital_id,
            account=account or original.account,
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
            description="Balance reversal test fixture",
        )

    # Test 1
    def test_account_balance_list(self):

        self.client.force_login(self.user_a)

        response = self.client.get(self.URL)

        self.assertEqual(
            response.status_code,
            200,
            response.content,
        )

        data = response.json()

        self.assertEqual(data["count"], 2)

        self.assertEqual(
            data["hospital_id"],
            str(self.hospital_a.pk),
        )

        accounts = {
            account["id"]: account
            for account in data["accounts"]
        }

        self.assert_balance(
            accounts[str(self.account_a.pk)],
            "10000.00",
            "800.00",
            "10800.00",
        )

        self.assert_balance(
            accounts[str(self.account_a2.pk)],
            "5000.00",
            "0.00",
            "5000.00",
        )

    # Test 2
    def test_individual_account_balance(self):

        data = self.get_balance(self.account_a)

        self.assert_balance(
            data,
            "10000.00",
            "800.00",
            "10800.00",
        )

        data = self.get_balance(self.account_a2)

        self.assert_balance(
            data,
            "5000.00",
            "0.00",
            "5000.00",
        )

    # Test 3
    def test_account_without_transactions(self):

        for opening in ("0.00", "1250.75"):

            with self.subTest(opening=opening):

                account = self.new_account(
                    opening=opening
                )

                data = self.get_balance(account)

                self.assert_balance(
                    data,
                    opening,
                    "0.00",
                    opening,
                )

    # Test 4
    def test_negative_balance(self):

        account = self.new_account(
            opening="100.00"
        )

        self.add_expense(
            account,
            "150.25",
        )

        data = self.get_balance(account)

        self.assert_balance(
            data,
            "100.00",
            "-150.25",
            "-50.25",
        )

    # Test 5
    def test_inactive_account_balance(self):

        account = self.new_account(
            opening="2000.00",
            active=False,
        )

        data = self.get_balance(account)

        self.assertFalse(data["is_active"])

        self.assert_balance(
            data,
            "2000.00",
            "0.00",
            "2000.00",
        )

    # Test 6
    def test_reversal_direction(self):

        # Synthetic fixtures test the balance formula.
        # No new reversal workflow is introduced.

        self.add_reversal(self.income)

        data = self.get_balance(self.account_a)

        self.assert_balance(
            data,
            "10000.00",
            "-200.00",
            "9800.00",
        )

        self.add_reversal(self.refund)

        data = self.get_balance(self.account_a)

        self.assert_balance(
            data,
            "10000.00",
            "0.00",
            "10000.00",
        )

    # Test 7
    def test_invalid_reversal_amount_rejected(self):

        self.add_reversal(
            self.income,
            amount="999.00",
        )

        self.client.force_login(self.user_a)

        for url in (
            self.URL,
            self.detail_url(self.account_a),
        ):

            response = self.client.get(url)

            self.assertEqual(
                response.status_code,
                409,
                response.content,
            )

    # Test 8
    def test_invalid_reversal_account_rejected(self):

        self.add_reversal(
            self.income,
            account=self.account_a2,
        )

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.detail_url(self.account_a2)
        )

        self.assertEqual(
            response.status_code,
            409,
            response.content,
        )

    # Test 9
    def test_cross_hospital_isolation(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            {"hospital_id": str(self.hospital_b.pk)},
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(
            data["hospital_id"],
            str(self.hospital_a.pk),
        )

        self.assertEqual(
            {a["id"] for a in data["accounts"]},
            {
                str(self.account_a.pk),
                str(self.account_a2.pk),
            },
        )

        response = self.client.get(
            self.detail_url(self.account_b)
        )

        self.assertEqual(response.status_code, 404)

        data = self.get_balance(
            self.account_b,
            self.user_b,
        )

        self.assert_balance(
            data,
            "10000.00",
            "-400.00",
            "9600.00",
        )

        response = self.client.get(
            self.detail_url(self.account_a)
        )

        self.assertEqual(response.status_code, 404)

    # Test 10
    def test_read_access_for_all_roles(self):

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            with self.subTest(user=user.username):

                data = self.get_balance(
                    self.account_a,
                    user,
                )

                self.assertEqual(
                    data["current_balance"],
                    "10800.00",
                )

                response = self.client.get(
                    self.URL
                )

                self.assertEqual(
                    response.status_code,
                    200,
                )

    # Test 11
    def test_unauthorized_access(self):

        urls = (
            self.URL,
            self.detail_url(self.account_a),
        )

        self.client.logout()

        for url in urls:

            response = self.client.get(url)

            self.assertEqual(
                response.status_code,
                401,
            )

        self.client.force_login(
            self.no_membership
        )

        for url in urls:

            response = self.client.get(url)

            self.assertEqual(
                response.status_code,
                403,
            )

    # Test 12
    def test_missing_account_returns_404(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            f"/api/accounting/accounts/{uuid4()}/balance/"
        )

        self.assertEqual(response.status_code, 404)

    # Test 13
    def test_balance_pagination(self):

        Account.objects.bulk_create([
            Account(
                hospital_id=self.hospital_a.pk,
                name=f"Pagination Account {i:03d}",
                account_type="cash",
                account_number=str(uuid4()),
                opening_balance=Decimal("0.00"),
                is_active=True,
            )
            for i in range(99)
        ])

        self.client.force_login(self.user_a)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["count"], 101)
        self.assertEqual(len(data["accounts"]), 50)

        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

        response = self.client.get(
            self.URL,
            {"limit": 1000},
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(len(data["accounts"]), 100)
        self.assertEqual(data["count"], 101)

        response = self.client.get(
            self.URL,
            {"limit": 100, "offset": 100},
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(len(data["accounts"]), 1)
        self.assertIsNone(data["next"])

    # Test 14
    def test_balance_write_operations_blocked(self):

        before_accounts = list(
            Account.objects.order_by("pk").values()
        )

        before_ledger = list(
            Transaction.objects.order_by("pk").values()
        )

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            self.client.force_login(user)

            for url in (
                self.URL,
                self.detail_url(self.account_a),
            ):

                for method in (
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                ):

                    with self.subTest(
                        user=user.username,
                        method=method,
                        url=url,
                    ):

                        response = self.client.generic(
                            method,
                            url,
                            data='{"current_balance":"99999.00"}',
                            content_type="application/json",
                        )

                        self.assertIn(
                            response.status_code,
                            (403, 405),
                            response.content,
                        )

        self.assertEqual(
            before_accounts,
            list(Account.objects.order_by("pk").values()),
        )

        self.assertEqual(
            before_ledger,
            list(Transaction.objects.order_by("pk").values()),
        )
