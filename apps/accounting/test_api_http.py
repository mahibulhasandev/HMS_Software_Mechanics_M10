from base64 import b64encode

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.accounting.models import Account, AccountingMembership
from apps.hospitals.models import Hospital


class AccountingHTTPTests(TestCase):
    URL = "/api/accounting/accounts/"

    @classmethod
    def setUpTestData(cls):
        with connection.cursor() as cursor:
            cursor.execute("GRANT USAGE ON SCHEMA public TO hms_app")
            cursor.execute("GRANT SELECT ON accounts TO hms_app")

        cls.hospital_a = Hospital.objects.create(
            name="HTTP Hospital A",
            registration_number="HTTP-A",
            address="Address A",
            phone="100001",
            email="httpa@example.com",
            timezone="Asia/Dhaka",
        )
        cls.hospital_b = Hospital.objects.create(
            name="HTTP Hospital B",
            registration_number="HTTP-B",
            address="Address B",
            phone="100002",
            email="httpb@example.com",
            timezone="Asia/Dhaka",
        )

        User = get_user_model()
        cls.user_a = User.objects.create_user(
            username="http_accountant_a", password="test-pass-a"
        )
        cls.user_b = User.objects.create_user(
            username="http_accountant_b", password="test-pass-b"
        )
        cls.staff = User.objects.create_user(
            username="http_staff", password="test-pass-staff"
        )
        cls.no_membership = User.objects.create_user(
            username="http_no_membership"
        )

        for user, hospital, role in (
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

        for hospital, name, number in (
            (cls.hospital_a, "HTTP_ACCOUNT_A", "HTTP-A"),
            (cls.hospital_b, "HTTP_ACCOUNT_B", "HTTP-B"),
        ):
            Account.objects.create(
                hospital_id=hospital.pk,
                name=name,
                account_type="cash",
                account_number=number,
                opening_balance=0,
                is_active=True,
            )

    def test_anonymous_denied(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_no_membership_denied(self):
        self.client.force_login(self.no_membership)
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_hospital_a_cannot_read_b(self):
        self.client.force_login(self.user_a)
        response = self.client.get(
            self.URL,
            {"hospital_id": str(self.hospital_b.pk)},
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["hospital_id"],
            str(self.hospital_a.pk),
        )
        self.assertEqual(
            [item["name"] for item in response.json()["accounts"]],
            ["HTTP_ACCOUNT_A"],
        )

    def test_hospital_b_only_reads_b(self):
        self.client.force_login(self.user_b)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["name"] for item in response.json()["accounts"]],
            ["HTTP_ACCOUNT_B"],
        )

    def test_staff_read_only(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.URL).status_code, 200)
        self.assertEqual(
            self.client.post(self.URL, {}).status_code,
            403,
        )

    def test_basic_header_does_not_switch_session_identity(self):
        self.client.force_login(self.user_a)
        credentials = b64encode(
            b"http_accountant_b:test-pass-b"
        ).decode("ascii")

        response = self.client.get(
            self.URL,
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["hospital_id"],
            str(self.hospital_a.pk),
        )
