from apps.accounting._test_helpers import create_test_user
import json

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import (
    connection,
    connections,
    close_old_connections,
    IntegrityError,
    transaction,
)
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounting import expense_api

from apps.accounting.models import (
    Account,
    AccountingMembership,
    Expense,
    ExpenseCategory,
    Transaction,
)

from apps.hospitals.models import Hospital


URL = "/api/accounting/expenses/"


def prepare_fixtures(target):

    with connection.cursor() as cursor:

        cursor.execute(
            "GRANT USAGE ON SCHEMA public TO hms_app"
        )

        cursor.execute(
            "GRANT SELECT ON accounts, expense_categories, "
            "transactions TO hms_app"
        )

        cursor.execute(
            "GRANT SELECT, INSERT, UPDATE "
            "ON expenses TO hms_app"
        )

    for suffix in ("a", "b"):

        hospital = Hospital.objects.create(
            name=f"Idempotency Hospital {suffix}",
            registration_number=f"IDEM-{suffix}",
            address="Test address",
            phone="100001",
            email=f"idem-{suffix}@example.com",
            timezone="Asia/Dhaka",
        )

        user = create_test_user(

    email=f"idem_accountant_{suffix}@example.test",
)

        AccountingMembership.objects.create(
            user=user,
            hospital=hospital,
            role="accountant",
            is_active=True,
        )

        account = Account.objects.create(
            hospital_id=hospital.pk,
            name="Cash Account",
            account_type="cash",
            account_number=f"IDEM-CASH-{suffix}",
            opening_balance=Decimal("10000.00"),
            is_active=True,
        )

        category = ExpenseCategory.objects.create(
            hospital_id=hospital.pk,
            name="Office Supplies",
        )

        setattr(target, f"hospital_{suffix}", hospital)
        setattr(target, f"user_{suffix}", user)
        setattr(target, f"account_{suffix}", account)
        setattr(target, f"category_{suffix}", category)

    for role in ("admin", "staff"):

        user = create_test_user(

    email=f"idem_{role}@example.test",
)

        AccountingMembership.objects.create(
            user=user,
            hospital=target.hospital_a,
            role=role,
            is_active=True,
        )

        setattr(target, role, user)

    target.no_membership = (
        create_test_user(

            email="idem_no_membership@example.test",
        )
    )

    target.today = timezone.localdate()


def make_payload(target, suffix="a", **overrides):

    data = {
        "expense_category_id": str(
            getattr(target, f"category_{suffix}").pk
        ),
        "account_id": str(
            getattr(target, f"account_{suffix}").pk
        ),
        "amount": "5000.00",
        "description": "Office supply purchase",
        "expense_date": target.today.isoformat(),
    }

    data.update(overrides)

    return data


def post_expense(client, payload, key=None):

    headers = {}

    if key is not None:

        headers["HTTP_IDEMPOTENCY_KEY"] = str(key)

    return client.post(
        URL,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


class ExpenseIdempotencyHTTPTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        prepare_fixtures(cls)

    def setUp(self):

        self.client.force_login(self.user_a)

    def expenses(self):

        return Expense.objects.filter(
            hospital_id=self.hospital_a.pk
        )

    def assert_status(self, response, expected):

        self.assertEqual(
            response.status_code,
            expected,
            response.content,
        )

    # Test 1
    def test_same_key_same_payload_replayed(self):

        key = uuid4()

        first = post_expense(
            self.client, make_payload(self), key
        )

        self.assert_status(first, 201)

        self.assertEqual(
            first["Idempotency-Replayed"], "false"
        )

        retry = post_expense(
            self.client,
            make_payload(
                self,
                amount="5000.0",
                description="  Office supply purchase  ",
            ),
            key,
        )

        self.assert_status(retry, 200)

        self.assertEqual(
            retry["Idempotency-Replayed"], "true"
        )

        self.assertEqual(
            first.json()["expense"]["id"],
            retry.json()["expense"]["id"],
        )

        self.assertEqual(self.expenses().count(), 1)

        expense = self.expenses().get()

        self.assertEqual(expense.idempotency_key, key)

        self.assertEqual(
            len(expense.request_fingerprint), 64
        )

        self.assertEqual(expense.status, "draft")

        self.assertEqual(
            expense.amount, Decimal("5000.00")
        )

        self.assertFalse(
            Transaction.objects.filter(
                hospital_id=self.hospital_a.pk
            ).exists()
        )

    # Test 2
    def test_different_keys_create_separate_expenses(self):

        payload = make_payload(self)

        first = post_expense(
            self.client, payload, uuid4()
        )

        second = post_expense(
            self.client, payload, uuid4()
        )

        self.assert_status(first, 201)
        self.assert_status(second, 201)

        self.assertNotEqual(
            first.json()["expense"]["id"],
            second.json()["expense"]["id"],
        )

        self.assertEqual(self.expenses().count(), 2)

    # Test 3
    def test_changed_payload_conflicts(self):

        key = uuid4()

        first = post_expense(
            self.client, make_payload(self), key
        )

        self.assert_status(first, 201)

        changes = (
            {"amount": "6000.00"},
            {"description": "Different description"},
            {"account_id": str(uuid4())},
            {"expense_category_id": str(uuid4())},
            {
                "expense_date": (
                    self.today - timedelta(days=1)
                ).isoformat()
            },
        )

        for change in changes:

            with self.subTest(change=change):

                response = post_expense(
                    self.client,
                    make_payload(self, **change),
                    key,
                )

                self.assert_status(response, 409)

        self.assertEqual(self.expenses().count(), 1)

        self.assertEqual(
            self.expenses().get().amount,
            Decimal("5000.00"),
        )

    # Test 4
    def test_different_actor_conflicts(self):

        key = uuid4()
        payload = make_payload(self)

        self.assert_status(
            post_expense(self.client, payload, key),
            201,
        )

        self.client.force_login(self.admin)

        self.assert_status(
            post_expense(self.client, payload, key),
            409,
        )

        self.assertEqual(self.expenses().count(), 1)

    # Test 5
    def test_same_key_allowed_in_different_hospitals(self):

        key = uuid4()

        first = post_expense(
            self.client, make_payload(self), key
        )

        self.assert_status(first, 201)

        self.client.force_login(self.user_b)

        second = post_expense(
            self.client,
            make_payload(self, suffix="b"),
            key,
        )

        self.assert_status(second, 201)

        self.assertNotEqual(
            first.json()["expense"]["id"],
            second.json()["expense"]["id"],
        )

        self.assertEqual(
            Expense.objects.filter(
                idempotency_key=key
            ).count(),
            2,
        )

    # Test 6
    def test_invalid_idempotency_key(self):

        for key in ("", "invalid-key", "123"):

            with self.subTest(key=key):

                response = post_expense(
                    self.client,
                    make_payload(self),
                    key,
                )

                self.assert_status(response, 400)

        self.assertEqual(self.expenses().count(), 0)

    # Test 7
    def test_failed_request_does_not_reserve_key(self):

        key = uuid4()

        response = post_expense(
            self.client,
            make_payload(self, amount="-100.00"),
            key,
        )

        self.assert_status(response, 400)

        response = post_expense(
            self.client,
            make_payload(
                self,
                account_id=str(self.account_b.pk),
            ),
            key,
        )

        self.assert_status(response, 404)

        self.assertEqual(self.expenses().count(), 0)

        response = post_expense(
            self.client, make_payload(self), key
        )

        self.assert_status(response, 201)

        self.assertEqual(self.expenses().count(), 1)

    # Test 8
    def test_legacy_request_without_key(self):

        payload = make_payload(self)

        for _ in range(2):

            response = post_expense(
                self.client, payload
            )

            self.assert_status(response, 201)

        self.assertEqual(self.expenses().count(), 2)

        self.assertEqual(
            self.expenses().filter(
                idempotency_key__isnull=True,
                request_fingerprint__isnull=True,
            ).count(),
            2,
        )

    # Test 9
    def test_replay_after_expense_status_changes(self):

        key = uuid4()
        payload = make_payload(self)

        first = post_expense(
            self.client, payload, key
        )

        self.assert_status(first, 201)

        expense_id = first.json()["expense"]["id"]

        submitted = self.client.post(
            f"{URL}{expense_id}/submit/",
            data="{}",
            content_type="application/json",
        )

        self.assert_status(submitted, 200)

        retry = post_expense(
            self.client, payload, key
        )

        self.assert_status(retry, 200)

        self.assertEqual(
            retry.json()["expense"]["id"],
            expense_id,
        )

        self.assertEqual(
            retry.json()["expense"]["status"],
            "pending_approval",
        )

        self.assertEqual(self.expenses().count(), 1)

    # Test 10
    def test_omitted_date_retry_on_next_day(self):

        key = uuid4()
        payload = make_payload(self)

        payload.pop("expense_date")

        with patch(
            "apps.accounting.services.timezone.localdate",
            return_value=self.today,
        ):

            first = post_expense(
                self.client, payload, key
            )

        self.assert_status(first, 201)

        with patch(
            "apps.accounting.services.timezone.localdate",
            return_value=self.today + timedelta(days=1),
        ):

            retry = post_expense(
                self.client, payload, key
            )

        self.assert_status(retry, 200)

        self.assertEqual(
            first.json()["expense"]["id"],
            retry.json()["expense"]["id"],
        )

        self.assertEqual(
            retry.json()["expense"]["expense_date"],
            self.today.isoformat(),
        )

        self.assertEqual(self.expenses().count(), 1)

    # Test 11
    def test_unauthorized_requests_do_not_create_expenses(self):

        key = uuid4()
        payload = make_payload(self)

        self.client.logout()

        self.assert_status(
            post_expense(self.client, payload, key),
            401,
        )

        for user in (
            self.staff,
            self.no_membership,
        ):

            self.client.force_login(user)

            self.assert_status(
                post_expense(self.client, payload, key),
                403,
            )

        self.assertEqual(self.expenses().count(), 0)

    def direct_create(self, key, fingerprint):

        return Expense.objects.create(
            hospital_id=self.hospital_a.pk,
            expense_category=self.category_a,
            account=self.account_a,
            amount=Decimal("100.00"),
            expense_date=self.today,
            description="Database constraint fixture",
            status="draft",
            idempotency_key=key,
            request_fingerprint=fingerprint,
        )

    # Test 12
    def test_database_unique_constraint(self):

        key = uuid4()

        self.direct_create(key, "a" * 64)

        with self.assertRaises(IntegrityError) as caught:

            with transaction.atomic():

                self.direct_create(key, "b" * 64)

        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            "uq_expense_hospital_idem_key",
        )

        self.assertEqual(self.expenses().count(), 1)

    # Test 13
    def test_database_field_pair_constraint(self):

        for key, fingerprint in (
            (uuid4(), None),
            (None, "a" * 64),
        ):

            with self.subTest(
                key=key,
                fingerprint=fingerprint,
            ):

                with self.assertRaises(IntegrityError) as caught:

                    with transaction.atomic():

                        self.direct_create(
                            key, fingerprint
                        )

                self.assertEqual(
                    caught.exception.__cause__.diag.constraint_name,
                    "ck_expense_idem_fields_pair",
                )

        self.assertEqual(self.expenses().count(), 0)


class ExpenseIdempotencyConcurrencyTests(TransactionTestCase):

    def _fixture_teardown(self, *args, **kwargs):

        # Only allow this cleanup in a Django test database.

        database_name = str(
            connection.settings_dict["NAME"]
        )

        if not database_name.startswith("test_"):

            raise RuntimeError(
                "Refusing cleanup outside a test database."
            )

        with transaction.atomic():

            with connection.cursor() as cursor:

                cursor.execute("SELECT current_database()")

                actual_database = cursor.fetchone()[0]

                if actual_database != database_name:

                    raise RuntimeError(
                        "Test database verification failed."
                    )

                cursor.execute("""
                    SELECT
                        n.nspname,
                        c.relname,
                        t.tgname,
                        t.tgenabled
                    FROM pg_trigger t
                    JOIN pg_class c
                        ON c.oid = t.tgrelid
                    JOIN pg_namespace n
                        ON n.oid = c.relnamespace
                    JOIN pg_proc p
                        ON p.oid = t.tgfoid
                    WHERE t.tgrelid = to_regclass('transactions')
                    AND NOT t.tgisinternal
                    AND p.proname = 'accounting_block_ledger_change'
                    AND (t.tgtype & 32) = 32
                """)

                triggers = cursor.fetchall()

                if len(triggers) != 1:

                    raise RuntimeError(
                        "Expected exactly one ledger TRUNCATE trigger."
                    )

                schema, table, trigger, enabled = triggers[0]

                if enabled != "O":

                    raise RuntimeError(
                        "Unexpected ledger trigger state."
                    )

                quote = connection.ops.quote_name

                qualified_table = (
                    f"{quote(schema)}.{quote(table)}"
                )

                trigger_name = quote(trigger)

                cursor.execute(
                    f"ALTER TABLE {qualified_table} "
                    f"DISABLE TRIGGER {trigger_name}"
                )

            # Execute normal Django test database cleanup.

            super()._fixture_teardown(*args, **kwargs)

            with connection.cursor() as cursor:

                cursor.execute(
                    f"ALTER TABLE {qualified_table} "
                    f"ENABLE TRIGGER {trigger_name}"
                )



    def setUp(self):

        prepare_fixtures(self)

    def run_concurrent_requests(self, payloads, key):

        barrier = Barrier(2, timeout=15)

        original_create = expense_api.create_expense

        def synchronized_create(**kwargs):

            # Both requests reach this point after their
            # initial lookup finds no existing expense.

            barrier.wait()

            return original_create(**kwargs)

        clients = [Client(), Client()]

        for client in clients:

            client.force_login(self.user_a)

        def worker(client, payload):

            close_old_connections()

            try:

                response = post_expense(
                    client, payload, key
                )

                return (
                    response.status_code,
                    response.json(),
                    response.get("Idempotency-Replayed"),
                )

            finally:

                connections.close_all()

        with patch.object(
            expense_api,
            "create_expense",
            side_effect=synchronized_create,
        ):

            with ThreadPoolExecutor(
                max_workers=2
            ) as executor:

                futures = [
                    executor.submit(worker, client, payload)
                    for client, payload in zip(
                        clients, payloads
                    )
                ]

                return [
                    future.result(timeout=40)
                    for future in futures
                ]

    # Test 14
    def test_concurrent_identical_requests(self):

        key = uuid4()

        results = self.run_concurrent_requests(
            [
                make_payload(self),
                make_payload(self),
            ],
            key,
        )

        self.assertEqual(
            sorted(result[0] for result in results),
            [200, 201],
            results,
        )

        ids = {
            result[1]["expense"]["id"]
            for result in results
        }

        self.assertEqual(len(ids), 1)

        self.assertEqual(
            {result[2] for result in results},
            {"true", "false"},
        )

        self.assertEqual(
            Expense.objects.filter(
                hospital_id=self.hospital_a.pk,
                idempotency_key=key,
            ).count(),
            1,
        )

        self.assertFalse(
            Transaction.objects.filter(
                hospital_id=self.hospital_a.pk
            ).exists()
        )

    # Test 15
    def test_concurrent_different_payloads(self):

        key = uuid4()

        results = self.run_concurrent_requests(
            [
                make_payload(self, amount="5000.00"),
                make_payload(self, amount="6000.00"),
            ],
            key,
        )

        self.assertEqual(
            sorted(result[0] for result in results),
            [201, 409],
            results,
        )

        expenses = Expense.objects.filter(
            hospital_id=self.hospital_a.pk,
            idempotency_key=key,
        )

        self.assertEqual(expenses.count(), 1)

        winner = next(
            result[1]["expense"]
            for result in results
            if result[0] == 201
        )

        self.assertEqual(
            expenses.get().amount,
            Decimal(winner["amount"]),
        )

        self.assertFalse(
            Transaction.objects.filter(
                hospital_id=self.hospital_a.pk
            ).exists()
        )
