from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from apps.hospitals.models import Hospital
from apps.accounting.middleware import AccountingHospitalContextMiddleware
from apps.accounting.models import Account, AccountingMembership


class AccountingMiddlewareSecurityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # Permissions required in Django's temporary test database.
        with connection.cursor() as cursor:
            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE "
                "ON TABLE accounts TO hms_app"
            )


    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_user(
            username="security_accountant",
            password="test-password-only",
        )

    def call_accounting(self, user, handler=None):
        request = self.factory.get("/api/accounting/security-test/")
        request.user = user

        if handler is None:
            handler = lambda request: JsonResponse({"ok": True})

        middleware = AccountingHospitalContextMiddleware(handler)
        return middleware(request)

    def create_hospital(self, code):
        return Hospital.objects.create(
            name=f"Security Hospital {code}",
            registration_number=f"SECURITY-{code}",
            address=f"Address {code}",
            phone=f"10000{code}",
            email=f"security{code}@example.com",
            timezone="Asia/Dhaka",
        )

    def test_anonymous_user_denied(self):
        response = self.call_accounting(AnonymousUser())
        self.assertEqual(response.status_code, 401)

    def test_user_without_membership_denied(self):
        response = self.call_accounting(self.user)
        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_denied(self):
        hospital = self.create_hospital("A")

        AccountingMembership.objects.create(
            user=self.user,
            hospital=hospital,
            role=AccountingMembership.Role.ACCOUNTANT,
            is_active=False,
        )

        response = self.call_accounting(self.user)
        self.assertEqual(response.status_code, 403)

    def test_hospital_rls_isolation(self):
        hospital_a = self.create_hospital("A")
        hospital_b = self.create_hospital("B")

        AccountingMembership.objects.create(
            user=self.user,
            hospital=hospital_a,
            role=AccountingMembership.Role.ACCOUNTANT,
            is_active=True,
        )

        other_user = get_user_model().objects.create_user(
            username="security_other_accountant",
            password="test-password-only",
        )

        AccountingMembership.objects.create(
            user=other_user,
            hospital=hospital_b,
            role=AccountingMembership.Role.ACCOUNTANT,
            is_active=True,
        )

        account_a = Account.objects.create(
            hospital_id=hospital_a.pk,
            name="SECURITY_ACCOUNT_A",
            account_type="cash",
            account_number="SEC-A",
            opening_balance=0,
            is_active=True,
        )

        Account.objects.create(
            hospital_id=hospital_b.pk,
            name="SECURITY_ACCOUNT_B",
            account_type="cash",
            account_number="SEC-B",
            opening_balance=0,
            is_active=True,
        )

        def protected_handler(request):
            self.assertEqual(
                request.accounting_hospital_id,
                hospital_a.pk,
            )

            self.assertEqual(
                request.accounting_role,
                AccountingMembership.Role.ACCOUNTANT,
            )

            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                self.assertEqual(cursor.fetchone()[0], "hms_app")

            # Only this user's membership should be visible.
            self.assertEqual(
                AccountingMembership.objects.count(),
                1,
            )

            # Hospital B's account must be invisible.
            visible_ids = set(
                Account.objects.values_list("pk", flat=True)
            )
            self.assertEqual(visible_ids, {account_a.pk})

            # Inserting another hospital's account must fail.
            with self.assertRaisesMessage(
                DatabaseError, "row-level security"
            ):
                with transaction.atomic():
                    Account.objects.create(
                        hospital_id=hospital_b.pk,
                        name="FORBIDDEN_ACCOUNT",
                        account_type="cash",
                        account_number="FORBIDDEN",
                        opening_balance=0,
                        is_active=True,
                    )

            return JsonResponse({"ok": True})

        response = self.call_accounting(
            self.user,
            protected_handler,
        )

        self.assertEqual(response.status_code, 200)

        # Restricted role should not remain after the request.
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertNotEqual(cursor.fetchone()[0], "hms_app")

    def test_other_modules_unaffected(self):
        request = self.factory.get("/api/diagnostic/")
        request.user = AnonymousUser()

        middleware = AccountingHospitalContextMiddleware(
            lambda request: JsonResponse({"ok": True})
        )

        response = middleware(request)
        self.assertEqual(response.status_code, 200)
