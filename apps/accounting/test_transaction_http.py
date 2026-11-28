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
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceStatus,
    Transaction,
)

from apps.accounting.services import (
    process_payment,
    process_refund,
    reverse_paid_expense,
)

from apps.hospitals.models import Hospital


class TransactionHTTPTests(TestCase):

    URL = "/api/accounting/transactions/"

    @classmethod
    def setUpTestData(cls):

        with connection.cursor() as cursor:
            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT ON transactions TO hms_app"
            )

        User = get_user_model()

        cls.admin_a = create_test_user(
            email='ledger_admin_a@example.test'
        )

        cls.user_a = create_test_user(
            email='ledger_accountant_a@example.test'
        )

        cls.user_b = create_test_user(
            email='ledger_accountant_b@example.test'
        )

        cls.staff = create_test_user(
            email='ledger_staff@example.test'
        )

        cls.no_membership = create_test_user(
            email='ledger_no_membership@example.test'
        )

        cls.hospital_a = Hospital.objects.create(
            name="Ledger Hospital A",
            registration_number="LEDGER-HOSP-A",
            address="Address A",
            phone="100001",
            email="ledgera@example.com",
            timezone="Asia/Dhaka",
        )

        cls.hospital_b = Hospital.objects.create(
            name="Ledger Hospital B",
            registration_number="LEDGER-HOSP-B",
            address="Address B",
            phone="100002",
            email="ledgerb@example.com",
            timezone="Asia/Dhaka",
        )

        for user, hospital, role in (
            (cls.admin_a, cls.hospital_a, "admin"),
            (cls.user_a, cls.hospital_a, "accountant"),
            (cls.user_b, cls.hospital_b, "accountant"),
            (cls.staff, cls.hospital_a, "staff"),
        ):

            AccountingMembership.objects.create(
                user=user,
                hospital=hospital,
                role=role,
                is_active=True,
            )

        cls.actor = AccountingMembership.objects.get(
            user=cls.user_a
        ).actor_uuid

        cls.approver = AccountingMembership.objects.get(
            user=cls.admin_a
        ).actor_uuid

        cls.today = timezone.localdate()
        cls.old_date = cls.today - timedelta(days=2)

        cls.account_a = Account.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Ledger Cash A",
            account_type="cash",
            account_number="LEDGER-ACC-A",
            opening_balance=Decimal("10000.00"),
            is_active=True,
        )

        cls.account_a2 = Account.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Ledger Bank A",
            account_type="bank",
            account_number="LEDGER-ACC-A2",
            opening_balance=Decimal("5000.00"),
            is_active=True,
        )

        cls.account_b = Account.objects.create(
            hospital_id=cls.hospital_b.pk,
            name="Ledger Cash B",
            account_type="cash",
            account_number="LEDGER-ACC-B",
            opening_balance=Decimal("10000.00"),
            is_active=True,
        )

        cls.category_a = ExpenseCategory.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Ledger Utilities A",
        )

        cls.category_b = ExpenseCategory.objects.create(
            hospital_id=cls.hospital_b.pk,
            name="Ledger Utilities B",
        )

        invoice = Invoice.objects.create(
            hospital_id=cls.hospital_a.pk,
            created_by_hospital_user_id=cls.actor,
            invoice_number="LEDGER-INV-A",
            subtotal=Decimal("1000.00"),
            discount=Decimal("0.00"),
            total=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status=InvoiceStatus.ISSUED,
            issued_at=timezone.now(),
        )

        payment_id = uuid4()

        process_payment(
            payment_id=payment_id,
            hospital_id=cls.hospital_a.pk,
            invoice_id=invoice.pk,
            account_id=cls.account_a.pk,
            received_by_hospital_user_id=cls.actor,
            amount="1000.00",
            method="cash",
            reference_no="LEDGER-PAY-001",
        )

        cls.income = Transaction.objects.get(
            payment_id=payment_id
        )

        refund_id = uuid4()

        process_refund(
            refund_id=refund_id,
            hospital_id=cls.hospital_a.pk,
            original_payment_id=payment_id,
            received_by_hospital_user_id=cls.actor,
            amount="200.00",
            method="cash",
            reference_no="LEDGER-REFUND-001",
        )

        cls.refund = Transaction.objects.get(
            payment_id=refund_id
        )

        expense_a = Expense.objects.create(
            hospital_id=cls.hospital_a.pk,
            expense_category=cls.category_a,
            account=cls.account_a2,
            amount=Decimal("300.00"),
            expense_date=cls.old_date,
            description="Electricity bill",
            status="paid",
            approved_by_hospital_user_id=cls.approver,
        )

        cls.expense = Transaction.objects.create(
            hospital_id=cls.hospital_a.pk,
            account=cls.account_a2,
            expense_category=cls.category_a,
            expense=expense_a,
            transaction_type="expense",
            amount=Decimal("300.00"),
            transaction_date=cls.old_date,
            description="Electricity bill",
        )

        reverse_paid_expense(
            expense_id=expense_a.pk,
            hospital_id=cls.hospital_a.pk,
            return_reference="LEDGER-RETURN-001",
            reason="Supplier returned funds",
        )

        cls.reversal = Transaction.objects.get(
            reversed_transaction=cls.expense
        )

        expense_b = Expense.objects.create(
            hospital_id=cls.hospital_b.pk,
            expense_category=cls.category_b,
            account=cls.account_b,
            amount=Decimal("400.00"),
            expense_date=cls.today,
            description="Hospital B expense",
            status="paid",
            approved_by_hospital_user_id=(
                AccountingMembership.objects.get(
                    user=cls.user_b
                ).actor_uuid
            ),
        )

        cls.transaction_b = Transaction.objects.create(
            hospital_id=cls.hospital_b.pk,
            account=cls.account_b,
            expense_category=cls.category_b,
            expense=expense_b,
            transaction_type="expense",
            amount=Decimal("400.00"),
            transaction_date=cls.today,
            description="Hospital B expense",
        )

    def detail_url(self, ledger):

        return f"{self.URL}{ledger.pk}/"

    def ids(self, response):

        self.assertEqual(
            response.status_code, 200, response.content
        )

        return {
            item["id"]
            for item in response.json()["transactions"]
        }

    # Test 1
    def test_all_roles_can_read(self):

        for user in (
            self.admin_a,
            self.user_a,
            self.staff,
        ):

            with self.subTest(user=user.email):

                self.client.force_login(user)

                response = self.client.get(self.URL)

                self.assertEqual(
                    response.status_code, 200, response.content
                )

                self.assertEqual(
                    response.json()["count"], 4
                )

                response = self.client.get(
                    self.detail_url(self.income)
                )

                self.assertEqual(response.status_code, 200)

    # Test 2
    def test_list_hospital_isolation(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            {"hospital_id": str(self.hospital_b.pk)},
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )

        expected = {
            str(self.income.pk),
            str(self.refund.pk),
            str(self.expense.pk),
            str(self.reversal.pk),
        }

        self.assertEqual(self.ids(response), expected)

        self.assertEqual(
            response.json()["hospital_id"],
            str(self.hospital_a.pk),
        )

        self.client.force_login(self.user_b)

        response = self.client.get(self.URL)

        self.assertEqual(
            self.ids(response),
            {str(self.transaction_b.pk)},
        )

    # Test 3
    def test_cross_hospital_detail_denied(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.detail_url(self.transaction_b)
        )

        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.user_b)

        response = self.client.get(
            self.detail_url(self.income)
        )

        self.assertEqual(response.status_code, 404)

    # Test 4
    def test_transaction_detail_fields(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.detail_url(self.reversal)
        )

        self.assertEqual(
            response.status_code, 200, response.content
        )

        data = response.json()["transaction"]

        self.assertEqual(data["id"], str(self.reversal.pk))
        self.assertEqual(data["transaction_type"], "reversal")

        self.assertEqual(
            data["reversed_transaction_id"],
            str(self.expense.pk),
        )

        self.assertEqual(
            Decimal(str(data["amount"])),
            Decimal("300.00"),
        )

        self.assertEqual(
            data["account_id"],
            str(self.account_a2.pk),
        )

        self.assertIsNone(data["payment_id"])
        self.assertIsNone(data["expense_id"])

    # Test 5
    def test_transaction_type_filter(self):

        self.client.force_login(self.user_a)

        for ledger in (
            self.income,
            self.refund,
            self.expense,
            self.reversal,
        ):

            with self.subTest(kind=ledger.transaction_type):

                response = self.client.get(
                    self.URL,
                    {"transaction_type": ledger.transaction_type},
                )

                self.assertEqual(
                    self.ids(response), {str(ledger.pk)}
                )

    # Test 6
    def test_account_filter(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            {"account_id": str(self.account_a.pk)},
        )

        self.assertEqual(
            self.ids(response),
            {
                str(self.income.pk),
                str(self.refund.pk),
            },
        )

        response = self.client.get(
            self.URL,
            {"account_id": str(self.account_a2.pk)},
        )

        self.assertEqual(
            self.ids(response),
            {
                str(self.expense.pk),
                str(self.reversal.pk),
            },
        )

        response = self.client.get(
            self.URL,
            {"account_id": str(self.account_b.pk)},
        )

        self.assertEqual(self.ids(response), set())

    # Test 7
    def test_date_range_filter(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            self.URL,
            {
                "date_from": self.old_date.isoformat(),
                "date_to": self.old_date.isoformat(),
            },
        )

        self.assertEqual(
            self.ids(response),
            {str(self.expense.pk)},
        )

        response = self.client.get(
            self.URL,
            {
                "date_from": self.today.isoformat(),
                "date_to": self.today.isoformat(),
            },
        )

        self.assertEqual(
            self.ids(response),
            {
                str(self.income.pk),
                str(self.refund.pk),
                str(self.reversal.pk),
            },
        )

    # Test 8
    def test_invalid_filters_rejected(self):

        self.client.force_login(self.user_a)

        for params in (
            {"transaction_type": "invalid"},
            {"account_id": "invalid-uuid"},
            {"date_from": "invalid-date"},
            {"date_to": "2026-02-30"},
            {
                "date_from": "2026-12-31",
                "date_to": "2026-01-01",
            },
        ):

            with self.subTest(params=params):

                response = self.client.get(
                    self.URL, params
                )

                self.assertEqual(
                    response.status_code, 400, response.content
                )

    # Test 9
    def test_pagination(self):

        self.client.force_login(self.user_a)

        returned_ids = []

        for offset in range(4):

            response = self.client.get(
                self.URL,
                {"limit": 1, "offset": offset},
            )

            self.assertEqual(
                response.status_code, 200, response.content
            )

            data = response.json()

            self.assertEqual(data["count"], 4)
            self.assertEqual(len(data["transactions"]), 1)

            returned_ids.append(
                data["transactions"][0]["id"]
            )

            if offset == 0:
                self.assertIsNone(data["previous"])
            else:
                self.assertIsNotNone(data["previous"])

            if offset == 3:
                self.assertIsNone(data["next"])
            else:
                self.assertIsNotNone(data["next"])

        expected = [
            str(pk)
            for pk in Transaction.objects.filter(
                hospital_id=self.hospital_a.pk
            ).order_by(
                "-transaction_date", "-id"
            ).values_list("pk", flat=True)
        ]

        self.assertEqual(returned_ids, expected)

    # Test 10
    def test_anonymous_access_denied(self):

        for url in (
            self.URL,
            self.detail_url(self.income),
        ):

            response = self.client.get(url)

            self.assertEqual(response.status_code, 401)

    # Test 11
    def test_no_membership_access_denied(self):

        self.client.force_login(self.no_membership)

        for url in (
            self.URL,
            self.detail_url(self.income),
        ):

            response = self.client.get(url)

            self.assertEqual(response.status_code, 403)

    # Test 12
    def test_missing_transaction_returns_404(self):

        self.client.force_login(self.user_a)

        response = self.client.get(
            f"{self.URL}{uuid4()}/"
        )

        self.assertEqual(response.status_code, 404)

    # Test 13
    def test_ledger_write_operations_blocked(self):

        before = list(
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
                self.detail_url(self.income),
            ):

                for method in (
                    "POST", "PUT", "PATCH", "DELETE"
                ):

                    with self.subTest(
                        user=user.email,
                        method=method,
                        url=url,
                    ):

                        response = self.client.generic(
                            method,
                            url,
                            data='{"amount":"9999.00"}',
                            content_type="application/json",
                        )

                        self.assertIn(
                            response.status_code,
                            (403, 405),
                            response.content,
                        )

        after = list(
            Transaction.objects.order_by("pk").values()
        )

        self.assertEqual(before, after)
