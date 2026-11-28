from apps.accounting._test_helpers import create_test_user
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.accounting.models import (
    Account,
    AccountingMembership,
    ExpenseCategory,
    Expense,
    Transaction,
)

from apps.hospitals.models import Hospital


class ExpenseHTTPTests(TestCase):

    URL = "/api/accounting/expenses/"

    @classmethod
    def setUpTestData(cls):

        with connection.cursor() as cursor:

            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT, UPDATE ON accounts TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT ON expense_categories TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE ON expenses TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT, INSERT ON transactions TO hms_app"
            )

        User = get_user_model()

        cls.user_a = create_test_user(
            email="expense_accountant_a@example.test",
        )

        cls.user_b = create_test_user(
            email="expense_accountant_b@example.test",
        )

        cls.admin_a = create_test_user(
            email="expense_admin_a@example.test",
        )

        cls.staff = create_test_user(
            email="expense_staff@example.test",
        )

        cls.no_membership = create_test_user(
            email="expense_no_membership@example.test",
        )

        cls.hospital_a = Hospital.objects.create(
            name="Expense Hospital A",
            registration_number="EXP-HOSP-A",
            address="Address A",
            phone="100001",
            email="expense_accountant_a@example.test",
            timezone="Asia/Dhaka",
        )

        cls.hospital_b = Hospital.objects.create(
            name="Expense Hospital B",
            registration_number="EXP-HOSP-B",
            address="Address B",
            phone="100002",
            email="expense_accountant_b@example.test",
            timezone="Asia/Dhaka",
        )

        for user, hospital, role in (
            (cls.user_a, cls.hospital_a, "accountant"),
            (cls.user_b, cls.hospital_b, "accountant"),
            (cls.admin_a, cls.hospital_a, "admin"),
            (cls.staff, cls.hospital_a, "staff"),
        ):

            AccountingMembership.objects.create(
                user=user,
                hospital=hospital,
                role=role,
                is_active=True,
            )

        cls.account_a = Account.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Expense Cash A",
            account_type="cash",
            account_number="EXP-ACC-A",
            opening_balance=Decimal("10000.00"),
            is_active=True,
        )

        cls.account_b = Account.objects.create(
            hospital_id=cls.hospital_b.pk,
            name="Expense Cash B",
            account_type="cash",
            account_number="EXP-ACC-B",
            opening_balance=Decimal("10000.00"),
            is_active=True,
        )

        cls.category_a = ExpenseCategory.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Utilities A",
        )

        cls.category_b = ExpenseCategory.objects.create(
            hospital_id=cls.hospital_b.pk,
            name="Utilities B",
        )

    def post(self, user, url, data):

        self.client.force_login(user)

        return self.client.post(
            url,
            data,
            content_type="application/json",
        )

    def expense_data(self, **overrides):

        data = {
            "expense_category_id": str(self.category_a.pk),
            "account_id": str(self.account_a.pk),
            "amount": "500.00",
            "description": "Electricity bill",
        }

        data.update(overrides)

        return data

    def create_draft(self):

        response = self.post(
            self.user_a,
            self.URL,
            self.expense_data(),
        )

        self.assertEqual(
            response.status_code, 201, response.content
        )

        return response.json()["expense"]["id"]

    def action(self, user, expense_id, action, data=None):

        return self.post(
            user,
            f"{self.URL}{expense_id}/{action}/",
            data if data is not None else {},
        )

    def approve_draft(self):

        expense_id = self.create_draft()

        response = self.action(
            self.user_a, expense_id, "submit"
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        response = self.action(
            self.admin_a, expense_id, "approve"
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        return expense_id

    def create_paid_expense(self):

        expense_id = self.approve_draft()

        response = self.action(
            self.user_a,
            expense_id,
            "pay",
            {"payment_confirmed": True},
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        return expense_id

    # Test 1
    def test_create_draft_expense(self):

        expense_id = self.create_draft()

        expense = Expense.objects.get(pk=expense_id)

        self.assertEqual(expense.status, "draft")
        self.assertEqual(expense.amount, Decimal("500.00"))
        self.assertEqual(
            expense.hospital_id, self.hospital_a.pk
        )

        self.assertEqual(Transaction.objects.count(), 0)

    # Test 2
    def test_submit_and_approve(self):

        expense_id = self.approve_draft()

        expense = Expense.objects.get(pk=expense_id)

        membership = AccountingMembership.objects.get(
            user=self.admin_a
        )

        self.assertEqual(expense.status, "approved")

        self.assertEqual(
            expense.approved_by_hospital_user_id,
            membership.actor_uuid,
        )

        self.assertEqual(Transaction.objects.count(), 0)

    # Test 3
    def test_payment_creates_ledger(self):

        expense_id = self.create_paid_expense()

        expense = Expense.objects.get(pk=expense_id)

        ledger = Transaction.objects.get(
            expense_id=expense_id
        )

        self.assertEqual(expense.status, "paid")
        self.assertEqual(ledger.transaction_type, "expense")
        self.assertEqual(ledger.amount, Decimal("500.00"))
        self.assertEqual(ledger.account_id, expense.account_id)
        self.assertEqual(ledger.hospital_id, expense.hospital_id)

        self.assertEqual(Transaction.objects.count(), 1)

    # Test 4
    def test_duplicate_payment_rejected(self):

        expense_id = self.create_paid_expense()

        response = self.action(
            self.user_a,
            expense_id,
            "pay",
            {"payment_confirmed": True},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transaction.objects.count(), 1)

    # Test 5
    def test_expense_reversal(self):

        expense_id = self.create_paid_expense()

        original = Transaction.objects.get(
            expense_id=expense_id
        )
        response = self.action(
            self.admin_a,
            expense_id,
            "reverse",
            {
                "return_confirmed": True,
                "return_reference": "RETURN-001",
                "reason": "Supplier returned payment",
            },
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        expense = Expense.objects.get(pk=expense_id)

        reversal = Transaction.objects.get(
            reversed_transaction=original
        )

        self.assertEqual(expense.status, "reversed")
        self.assertEqual(reversal.transaction_type, "reversal")
        self.assertEqual(reversal.amount, original.amount)
        self.assertEqual(reversal.account_id, original.account_id)
        self.assertEqual(reversal.hospital_id, original.hospital_id)

        self.assertEqual(Transaction.objects.count(), 2)

    # Test 6
    def test_duplicate_reversal_rejected(self):

        expense_id = self.create_paid_expense()

        data = {
            "return_confirmed": True,
            "return_reference": "RETURN-002",
            "reason": "Returned payment",
        }

        first = self.action(
            self.admin_a, expense_id, "reverse", data
        )

        second = self.action(
            self.admin_a, expense_id, "reverse", data
        )

        self.assertEqual(
            first.status_code, 200, first.content
        )

        self.assertEqual(second.status_code, 400)
        self.assertEqual(Transaction.objects.count(), 2)

    # Test 7
    def test_reject_expense(self):

        expense_id = self.create_draft()

        submitted = self.action(
            self.user_a, expense_id, "submit"
        )

        self.assertEqual(submitted.status_code, 200)

        response = self.action(
            self.admin_a, expense_id, "reject"
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        expense = Expense.objects.get(pk=expense_id)

        self.assertEqual(expense.status, "rejected")
        self.assertEqual(Transaction.objects.count(), 0)

    # Test 8
    def test_invalid_status_transition(self):

        expense_id = self.create_draft()

        for user, action, data in (
            (self.admin_a, "approve", {}),
            (self.admin_a, "reject", {}),
            (
                self.user_a,
                "pay",
                {"payment_confirmed": True},
            ),
            (
                self.admin_a,
                "reverse",
                {
                    "return_confirmed": True,
                    "return_reference": "INVALID",
                    "reason": "Invalid reversal",
                },
            ),
        ):

            with self.subTest(action=action):

                response = self.action(
                    user, expense_id, action, data
                )

                self.assertEqual(
                    response.status_code, 400, response.content
                )

        self.assertEqual(
            Expense.objects.get(pk=expense_id).status,
            "draft",
        )

        self.assertEqual(Transaction.objects.count(), 0)

    # Test 9
    def test_cross_hospital_access_denied(self):

        expense_id = self.create_draft()

        response = self.action(
            self.user_b, expense_id, "submit"
        )

        self.assertEqual(response.status_code, 404)

        for overrides in (
            {"account_id": str(self.account_b.pk)},
            {"expense_category_id": str(self.category_b.pk)},
        ):

            response = self.post(
                self.user_a,
                self.URL,
                self.expense_data(**overrides),
            )

            self.assertEqual(response.status_code, 404)

        self.assertEqual(Expense.objects.count(), 1)

        self.assertEqual(
            Expense.objects.get(pk=expense_id).status,
            "draft",
        )

    # Test 10
    def test_role_restrictions(self):

        expense_id = self.create_draft()

        response = self.post(
            self.staff,
            self.URL,
            self.expense_data(),
        )

        self.assertEqual(response.status_code, 403)

        for action in (
            "submit", "approve", "reject", "pay", "reverse"
        ):

            response = self.action(
                self.staff, expense_id, action
            )

            self.assertEqual(response.status_code, 403)

        for action in ("approve", "reject", "reverse"):

            response = self.action(
                self.user_a, expense_id, action
            )

            self.assertEqual(response.status_code, 403)

    # Test 11
    def test_invalid_and_forged_input(self):

        for overrides in (
            {"amount": "-10.00"},
            {"amount": "0.00"},
            {"amount": "10.123"},
            {"amount": 10.25},
            {"description": ""},
            {"hospital_id": str(self.hospital_b.pk)},
            {"status": "paid"},
            {
                "approved_by_hospital_user_id": str(uuid4())
            },
        ):

            with self.subTest(overrides=overrides):

                response = self.post(
                    self.user_a,
                    self.URL,
                    self.expense_data(**overrides),
                )

                self.assertEqual(
                    response.status_code, 400, response.content
                )

        self.assertEqual(Expense.objects.count(), 0)

    # Test 12
    def test_confirmation_required(self):

        expense_id = self.approve_draft()

        response = self.action(
            self.user_a,
            expense_id,
            "pay",
            {"payment_confirmed": False},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transaction.objects.count(), 0)

        response = self.action(
            self.user_a,
            expense_id,
            "pay",
            {"payment_confirmed": True},
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        response = self.action(
            self.admin_a,
            expense_id,
            "reverse",
            {
                "return_confirmed": False,
                "return_reference": "RETURN-003",
                "reason": "Return not verified",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Transaction.objects.count(), 1)

        self.assertEqual(
            Expense.objects.get(pk=expense_id).status,
            "paid",
        )

    # Test 13
    def test_anonymous_and_no_membership_denied(self):

        self.client.logout()

        response = self.client.post(
            self.URL,
            self.expense_data(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

        response = self.post(
            self.no_membership,
            self.URL,
            self.expense_data(),
        )

        self.assertEqual(response.status_code, 403)

        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(Transaction.objects.count(), 0)


    # EXPENSE READ API TESTS

    def test_expense_read_access_for_all_roles(self):

        expense_id = self.create_draft()

        for user in (self.admin_a, self.user_a, self.staff):

            with self.subTest(user=str(user.pk)):

                self.client.force_login(user)

                response = self.client.get(self.URL)

                self.assertEqual(
                    response.status_code, 200, response.content
                )

                response = self.client.get(
                    f"{self.URL}{expense_id}/"
                )

                self.assertEqual(
                    response.status_code, 200, response.content
                )

                self.assertEqual(
                    response.json()["expense"]["id"],
                    expense_id,
                )

    def test_expense_list_hospital_isolation(self):

        expense_a = self.create_draft()

        response = self.post(
            self.user_b,
            self.URL,
            self.expense_data(
                account_id=str(self.account_b.pk),
                expense_category_id=str(self.category_b.pk),
            ),
        )

        self.assertEqual(
            response.status_code, 201, response.content
        )

        expense_b = response.json()["expense"]["id"]

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            {"hospital_id": str(self.hospital_b.pk)},
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        self.assertEqual(
            response.json()["hospital_id"],
            str(self.hospital_a.pk),
        )

        self.assertEqual(
            [e["id"] for e in response.json()["expenses"]],
            [expense_a],
        )

        self.client.force_login(self.user_b)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            [e["id"] for e in response.json()["expenses"]],
            [expense_b],
        )

    def test_expense_detail_cross_hospital_denied(self):

        expense_id = self.create_draft()

        self.client.force_login(self.user_b)

        response = self.client.get(
            f"{self.URL}{expense_id}/"
        )

        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.user_a)

        response = self.client.get(
            f"{self.URL}{uuid4()}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_expense_status_filter(self):

        draft_id = self.create_draft()
        paid_id = self.create_paid_expense()

        self.client.force_login(self.user_a)

        for status_value, expected_id in (
            ("draft", draft_id),
            ("paid", paid_id),
        ):

            with self.subTest(status=status_value):

                response = self.client.get(
                    self.URL,
                    {"status": status_value},
                )

                self.assertEqual(
                    response.status_code, 200, response.content
                )

                self.assertEqual(
                    response.json()["count"], 1
                )

                self.assertEqual(
                    response.json()["expenses"][0]["id"],
                    expected_id,
                )

    def test_expense_invalid_status_filter(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            {"status": "invalid_status"},
        )

        self.assertEqual(response.status_code, 400)

    def test_expense_pagination(self):

        expense_ids = {
            self.create_draft()
            for _ in range(3)
        }

        self.client.force_login(self.user_a)

        returned_ids = set()

        for offset in range(3):

            response = self.client.get(
                self.URL,
                {"limit": 1, "offset": offset},
            )

            self.assertEqual(
                response.status_code, 200, response.content
            )

            data = response.json()

            self.assertEqual(data["count"], 3)
            self.assertEqual(len(data["expenses"]), 1)

            returned_ids.add(data["expenses"][0]["id"])

            if offset == 0:
                self.assertIsNone(data["previous"])
            else:
                self.assertIsNotNone(data["previous"])

            if offset == 2:
                self.assertIsNone(data["next"])
            else:
                self.assertIsNotNone(data["next"])

        self.assertEqual(returned_ids, expense_ids)

    def test_expense_pagination_limits(self):

        from django.utils import timezone

        Expense.objects.bulk_create([
            Expense(
                hospital_id=self.hospital_a.pk,
                expense_category=self.category_a,
                account=self.account_a,
                amount=Decimal("100.00"),
                expense_date=timezone.localdate(),
                description=f"Pagination expense {i}",
                status="draft",
            )
            for i in range(101)
        ])

        self.client.force_login(self.user_a)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 101)
        self.assertEqual(
            len(response.json()["expenses"]), 50
        )

        response = self.client.get(
            self.URL,
            {"limit": 1000},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 101)
        self.assertEqual(
            len(response.json()["expenses"]), 100
        )

        self.assertIsNotNone(response.json()["next"])

    def test_expense_read_anonymous_denied(self):

        expense_id = self.create_draft()

        self.client.logout()

        for url in (
            self.URL,
            f"{self.URL}{expense_id}/",
        ):

            response = self.client.get(url)

            self.assertEqual(response.status_code, 401)

    def test_expense_read_no_membership_denied(self):

        expense_id = self.create_draft()

        self.client.force_login(self.no_membership)

        for url in (
            self.URL,
            f"{self.URL}{expense_id}/",
        ):

            response = self.client.get(url)

            self.assertEqual(response.status_code, 403)

    def test_expense_empty_list(self):

        self.client.force_login(self.user_a)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertEqual(data["count"], 0)
        self.assertEqual(data["expenses"], [])
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])
