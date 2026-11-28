from apps.accounting._test_helpers import create_test_user
from base64 import b64encode

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from apps.accounting.models import Account, AccountingMembership, IncomeCategory, ExpenseCategory
from apps.hospitals.models import Hospital


class AccountingHTTPTests(TestCase):
    URL = "/api/accounting/accounts/"

    @classmethod
    def setUpTestData(cls):
        with connection.cursor() as cursor:
            cursor.execute("GRANT USAGE ON SCHEMA public TO hms_app")
            cursor.execute("GRANT SELECT, INSERT, UPDATE ON accounts TO hms_app")
            cursor.execute("GRANT SELECT, INSERT ON income_categories TO hms_app")
            cursor.execute("GRANT SELECT, INSERT ON expense_categories TO hms_app")

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
        cls.user_a = create_test_user(
            email="http_accountant_a@example.test",
            password="test-pass-a",
        )
        cls.user_b = create_test_user(
            email="http_accountant_b@example.test",
            password="test-pass-b",
        )
        cls.staff = create_test_user(
            email="http_staff@example.test",
            password="test-pass-staff",
        )
        cls.no_membership = create_test_user(
            email="http_no_membership@example.test",
            password="test-pass-no-membership",
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


    def account_payload(self, number):
        return {
            "name": f"New Account {number}",
            "account_type": "cash",
            "account_number": number,
            "opening_balance": "0.00",
            "is_active": True,
        }

    def test_accountant_can_create_account(self):
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.URL,
            self.account_payload("NEW-A-001"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        account = Account.objects.get(account_number="NEW-A-001")
        self.assertEqual(account.hospital_id, self.hospital_a.pk)

    def test_admin_can_create_account(self):
        AccountingMembership.objects.filter(
            user=self.user_a
        ).update(role="admin")

        self.client.force_login(self.user_a)

        response = self.client.post(
            self.URL,
            self.account_payload("NEW-ADMIN-001"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)

    def test_staff_cannot_create_account(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            self.URL,
            self.account_payload("STAFF-BLOCKED"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Account.objects.filter(
                account_number="STAFF-BLOCKED"
            ).exists()
        )

    def test_forged_hospital_id_rejected(self):
        self.client.force_login(self.user_a)
        payload = self.account_payload("FORGED-HOSPITAL")
        payload["hospital_id"] = str(self.hospital_b.pk)

        response = self.client.post(
            self.URL,
            payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(
            Account.objects.filter(
                account_number="FORGED-HOSPITAL"
            ).exists()
        )

    def test_forged_hospital_header_ignored(self):
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.URL,
            self.account_payload("HEADER-A-001"),
            content_type="application/json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )

        self.assertEqual(response.status_code, 201, response.content)
        account = Account.objects.get(account_number="HEADER-A-001")
        self.assertEqual(account.hospital_id, self.hospital_a.pk)

    def test_post_without_csrf_is_rejected(self):
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user_a)

        response = csrf_client.post(
            self.URL,
            self.account_payload("NO-CSRF"),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_post_with_valid_csrf_succeeds(self):
        from django.conf import settings
        from django.middleware.csrf import get_token
        from django.test import Client, RequestFactory

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user_a)

        request = RequestFactory().get("/")
        csrf_token = get_token(request)

        csrf_client.cookies[settings.CSRF_COOKIE_NAME] = (
            request.META["CSRF_COOKIE"]
        )

        response = csrf_client.post(
            self.URL,
            self.account_payload("VALID-CSRF"),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 201, response.content)


    def test_category_anonymous_denied(self):
        for path in ("income-categories", "expense-categories"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/accounting/{path}/"
                )
                self.assertEqual(response.status_code, 401)

    def test_category_no_membership_denied(self):
        self.client.force_login(self.no_membership)
        for path in ("income-categories", "expense-categories"):
            with self.subTest(path=path):
                response = self.client.get(
                    f"/api/accounting/{path}/"
                )
                self.assertEqual(response.status_code, 403)

    def test_category_hospital_isolation(self):
        for model in (IncomeCategory, ExpenseCategory):
            model.objects.create(
                hospital_id=self.hospital_a.pk,
                name="CATEGORY_A",
            )
            model.objects.create(
                hospital_id=self.hospital_b.pk,
                name="CATEGORY_B",
            )

        for user, expected in (
            (self.user_a, "CATEGORY_A"),
            (self.user_b, "CATEGORY_B"),
        ):
            self.client.force_login(user)

            for path, key in (
                ("income-categories", "income_categories"),
                ("expense-categories", "expense_categories"),
            ):
                with self.subTest(user=user.email, path=path):
                    response = self.client.get(
                        f"/api/accounting/{path}/",
                        {"hospital_id": str(self.hospital_b.pk)},
                        HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        [x["name"] for x in response.json()[key]],
                        [expected],
                    )

    def test_category_admin_accountant_can_create(self):
        for role in ("accountant", "admin"):
            AccountingMembership.objects.filter(
                user=self.user_a
            ).update(role=role)

            self.client.force_login(self.user_a)

            for path, model in (
                ("income-categories", IncomeCategory),
                ("expense-categories", ExpenseCategory),
            ):
                with self.subTest(role=role, path=path):
                    name = f"{role}_{path}"

                    response = self.client.post(
                        f"/api/accounting/{path}/",
                        {"name": name},
                        content_type="application/json",
                    )

                    self.assertEqual(
                        response.status_code, 201, response.content
                    )
                    self.assertTrue(
                        model.objects.filter(
                            hospital_id=self.hospital_a.pk,
                            name=name,
                        ).exists()
                    )

    def test_category_staff_read_only(self):
        self.client.force_login(self.staff)

        for path in ("income-categories", "expense-categories"):
            with self.subTest(path=path):
                url = f"/api/accounting/{path}/"

                self.assertEqual(
                    self.client.get(url).status_code, 200
                )
                self.assertEqual(
                    self.client.post(
                        url,
                        {"name": "STAFF_FORBIDDEN"},
                        content_type="application/json",
                    ).status_code,
                    403,
                )

    def test_category_forged_hospital_id_rejected(self):
        self.client.force_login(self.user_a)

        for path, model in (
            ("income-categories", IncomeCategory),
            ("expense-categories", ExpenseCategory),
        ):
            with self.subTest(path=path):
                name = f"FORGED_{path}"
                response = self.client.post(
                    f"/api/accounting/{path}/",
                    {
                        "name": name,
                        "hospital_id": str(self.hospital_b.pk),
                    },
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertFalse(
                    model.objects.filter(name=name).exists()
                )

    def test_category_forged_header_ignored(self):
        self.client.force_login(self.user_a)

        for path, model in (
            ("income-categories", IncomeCategory),
            ("expense-categories", ExpenseCategory),
        ):
            with self.subTest(path=path):
                name = f"HEADER_{path}"
                response = self.client.post(
                    f"/api/accounting/{path}/",
                    {"name": name},
                    content_type="application/json",
                    HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
                )

                self.assertEqual(
                    response.status_code, 201, response.content
                )
                self.assertTrue(
                    model.objects.filter(
                        hospital_id=self.hospital_a.pk,
                        name=name,
                    ).exists()
                )

    def test_duplicate_expense_category_rejected(self):
        ExpenseCategory.objects.create(
            hospital_id=self.hospital_b.pk,
            name="Electricity",
        )

        self.client.force_login(self.user_a)
        url = "/api/accounting/expense-categories/"

        first = self.client.post(
            url,
            {"name": "Electricity"},
            content_type="application/json",
        )
        second = self.client.post(
            url,
            {"name": "Electricity"},
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 400, second.content)
        self.assertEqual(
            ExpenseCategory.objects.filter(
                hospital_id=self.hospital_a.pk,
                name="Electricity",
            ).count(),
            1,
        )

    def test_income_category_invalid_department_uuid(self):
        self.client.force_login(self.user_a)

        response = self.client.post(
            "/api/accounting/income-categories/",
            {
                "name": "Invalid Department",
                "department_id": "not-a-uuid",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
