
import uuid
from contextlib import contextmanager

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from apps.accounting.models import Account

class RLSSecurityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.hospital_a = uuid.uuid4()
        cls.hospital_b = uuid.uuid4()

        # Grant permissions in Django's temporary test database.
        with connection.cursor() as cursor:
            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE "
                "ON accounts TO hms_app"
            )

        cls.account_a = Account.objects.create(
            hospital_id=cls.hospital_a,
            name="RLS_TEST_A",
            account_type="cash",
            account_number="TEST-A",
            opening_balance=0,
            is_active=True,
        )

        cls.account_b = Account.objects.create(
            hospital_id=cls.hospital_b,
            name="RLS_TEST_B",
            account_type="cash",
            account_number="TEST-B",
            opening_balance=0,
            is_active=True,
        )

    @contextmanager
    def as_hospital(self, hospital_id=None):
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE hms_app")
                    cursor.execute(
                        "SELECT set_config("
                        "'app.hospital_id', %s, true)",
                        [str(hospital_id) if hospital_id else ""],
                    )
                yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def visible_accounts(self):
        return set(
            Account.objects.filter(
                name__startswith="RLS_TEST_"
            ).values_list("name", flat=True)
        )

    def test_no_hospital_context(self):
        with self.as_hospital():
            self.assertEqual(self.visible_accounts(), set())

    def test_hospital_a_isolation(self):
        with self.as_hospital(self.hospital_a):
            self.assertEqual(
                self.visible_accounts(),
                {"RLS_TEST_A"},
            )

    def test_hospital_b_isolation(self):
        with self.as_hospital(self.hospital_b):
            self.assertEqual(
                self.visible_accounts(),
                {"RLS_TEST_B"},
            )

    def test_cross_hospital_insert_blocked(self):
        with self.as_hospital(self.hospital_a):
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    Account.objects.create(
                        hospital_id=self.hospital_b,
                        name="RLS_TEST_BLOCKED",
                        account_type="cash",
                        account_number="BLOCKED",
                        opening_balance=0,
                        is_active=True,
                    )

    def test_cross_hospital_update_blocked(self):
        with self.as_hospital(self.hospital_a):
            with self.assertRaises(DatabaseError):
                with transaction.atomic():
                    Account.objects.filter(
                        pk=self.account_a.pk
                    ).update(
                        hospital_id=self.hospital_b
                    )