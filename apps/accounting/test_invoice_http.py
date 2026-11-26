from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    AccountingMembership,
    Invoice,
    InvoiceStatus,
)
from apps.hospitals.models import Hospital


class InvoiceListHTTPTests(TestCase):
    URL = "/api/accounting/invoices/"

    @classmethod
    def setUpTestData(cls):
        with connection.cursor() as cursor:
            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE ON invoices TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT, INSERT ON invoice_items TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT ON payments TO hms_app"
            )

        cls.hospital_a = Hospital.objects.create(
            name="Invoice Hospital A",
            registration_number="INV-HTTP-A",
            address="Address A",
            phone="100001",
            email="invoicea@example.com",
            timezone="Asia/Dhaka",
        )

        cls.hospital_b = Hospital.objects.create(
            name="Invoice Hospital B",
            registration_number="INV-HTTP-B",
            address="Address B",
            phone="100002",
            email="invoiceb@example.com",
            timezone="Asia/Dhaka",
        )

        User = get_user_model()

        cls.user_a = User.objects.create_user(
            username="invoice_accountant_a"
        )
        cls.user_b = User.objects.create_user(
            username="invoice_accountant_b"
        )
        cls.staff = User.objects.create_user(
            username="invoice_staff"
        )
        cls.no_membership = User.objects.create_user(
            username="invoice_no_membership"
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

        for hospital, number in (
            (cls.hospital_a, "INV-HTTP-001"),
            (cls.hospital_b, "INV-HTTP-002"),
        ):
            Invoice.objects.create(
                hospital_id=hospital.pk,
                created_by_hospital_user_id=uuid4(),
                invoice_number=number,
                subtotal=Decimal("0.00"),
                discount=Decimal("0.00"),
                total=Decimal("0.00"),
                amount_paid=Decimal("0.00"),
                status=InvoiceStatus.DRAFT,
                issued_at=timezone.now(),
            )

    def test_anonymous_denied(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 401)

    def test_no_membership_denied(self):
        self.client.force_login(self.no_membership)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 403)

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
            [x["invoice_number"] for x in response.json()["invoices"]],
            ["INV-HTTP-001"],
        )

    def test_hospital_b_cannot_read_a(self):
        self.client.force_login(self.user_b)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [x["invoice_number"] for x in response.json()["invoices"]],
            ["INV-HTTP-002"],
        )

    def test_staff_read_only(self):
        self.client.force_login(self.staff)

        self.assertEqual(
            self.client.get(self.URL).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(self.URL, {}).status_code,
            403,
        )


    def invoice_a(self):
        return Invoice.objects.get(invoice_number="INV-HTTP-001")

    def invoice_b(self):
        return Invoice.objects.get(invoice_number="INV-HTTP-002")

    def item_payload(self):
        return {
            "department_id": str(uuid4()),
            "description": "Consultation Fee",
            "quantity": 2,
            "unit_price": "250.00",
        }

    def action_url(self, invoice, action):
        return f"/api/accounting/invoices/{invoice.pk}/{action}/"

    def test_add_item_recalculates_total(self):
        invoice = self.invoice_a()
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.action_url(invoice, "items"),
            self.item_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)

        invoice.refresh_from_db()
        self.assertEqual(invoice.subtotal, Decimal("500.00"))
        self.assertEqual(invoice.total, Decimal("500.00"))
        self.assertEqual(invoice.status, InvoiceStatus.DRAFT)

    def test_issue_without_items_rejected(self):
        invoice = self.invoice_a()
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.action_url(invoice, "issue"),
            {},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.DRAFT)

    def test_issue_invoice_with_item(self):
        invoice = self.invoice_a()
        self.client.force_login(self.user_a)

        item_response = self.client.post(
            self.action_url(invoice, "items"),
            self.item_payload(),
            content_type="application/json",
        )
        self.assertEqual(item_response.status_code, 201, item_response.content)

        response = self.client.post(
            self.action_url(invoice, "issue"),
            {},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.ISSUED)
        self.assertEqual(invoice.total, Decimal("500.00"))

    def test_issued_invoice_rejects_new_item(self):
        invoice = self.invoice_a()
        invoice.status = InvoiceStatus.ISSUED
        invoice.save(update_fields=["status"])

        self.client.force_login(self.user_a)

        response = self.client.post(
            self.action_url(invoice, "items"),
            self.item_payload(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_void_unpaid_issued_invoice(self):
        invoice = self.invoice_a()
        invoice.status = InvoiceStatus.ISSUED
        invoice.save(update_fields=["status"])

        self.client.force_login(self.user_a)

        response = self.client.post(
            self.action_url(invoice, "void"),
            {},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.VOIDED)

    def test_other_hospital_actions_blocked(self):
        invoice = self.invoice_b()
        self.client.force_login(self.user_a)

        for action in ("items", "issue", "void"):
            with self.subTest(action=action):
                payload = self.item_payload() if action == "items" else {}

                response = self.client.post(
                    self.action_url(invoice, action),
                    payload,
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 404, response.content)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.DRAFT)
        self.assertEqual(invoice.total, Decimal("0.00"))

    def test_staff_cannot_modify_invoice(self):
        invoice = self.invoice_a()
        self.client.force_login(self.staff)

        for action in ("items", "issue", "void"):
            with self.subTest(action=action):
                payload = self.item_payload() if action == "items" else {}

                response = self.client.post(
                    self.action_url(invoice, action),
                    payload,
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 403, response.content)

    def test_invalid_invoice_item_rejected(self):
        invoice = self.invoice_a()
        self.client.force_login(self.user_a)

        for change in (
            {"quantity": 0},
            {"unit_price": "-10.00"},
            {"hospital_id": str(self.hospital_b.pk)},
        ):
            with self.subTest(change=change):
                payload = self.item_payload()
                payload.update(change)

                response = self.client.post(
                    self.action_url(invoice, "items"),
                    payload,
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400, response.content)

    def test_issue_rejects_unexpected_body(self):
        invoice = self.invoice_a()
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.action_url(invoice, "issue"),
            {"hospital_id": str(self.hospital_b.pk)},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400, response.content)


    def test_create_invoice_actor_identity(self):
        for user, hospital, number in (
            (self.user_a, self.hospital_a, "NEW-INV-A"),
            (self.user_b, self.hospital_b, "NEW-INV-B"),
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)

                response = self.client.post(
                    self.URL,
                    {"invoice_number": number},
                    content_type="application/json",
                )

                self.assertEqual(
                    response.status_code, 201, response.content
                )

                invoice = Invoice.objects.get(
                    invoice_number=number
                )
                membership = AccountingMembership.objects.get(
                    user=user
                )

                self.assertEqual(
                    invoice.hospital_id, hospital.pk
                )
                self.assertEqual(
                    invoice.created_by_hospital_user_id,
                    membership.actor_uuid,
                )
                self.assertEqual(
                    invoice.status, InvoiceStatus.DRAFT
                )
                self.assertEqual(
                    invoice.subtotal, Decimal("0.00")
                )
                self.assertEqual(
                    invoice.total, Decimal("0.00")
                )
                self.assertEqual(
                    invoice.amount_paid, Decimal("0.00")
                )

    def test_admin_can_create_invoice(self):
        AccountingMembership.objects.filter(
            user=self.user_a
        ).update(role="admin")

        self.client.force_login(self.user_a)

        response = self.client.post(
            self.URL,
            {"invoice_number": "ADMIN-INV-001"},
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code, 201, response.content
        )

    def test_staff_cannot_create_invoice(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            self.URL,
            {"invoice_number": "STAFF-INV"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Invoice.objects.filter(
                invoice_number="STAFF-INV"
            ).exists()
        )

    def test_no_membership_cannot_create_invoice(self):
        self.client.force_login(self.no_membership)

        response = self.client.post(
            self.URL,
            {"invoice_number": "NO-MEMBERSHIP-INV"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_forged_invoice_fields_rejected(self):
        self.client.force_login(self.user_a)

        forbidden_fields = {
            "hospital_id": str(self.hospital_b.pk),
            "created_by_hospital_user_id": str(uuid4()),
            "patient_id": str(uuid4()),
            "patient_visit_id": str(uuid4()),
            "subtotal": "9999.00",
            "total": "9999.00",
            "amount_paid": "9999.00",
            "status": "paid",
            "issued_at": timezone.now().isoformat(),
        }

        for field, value in forbidden_fields.items():
            with self.subTest(field=field):
                response = self.client.post(
                    self.URL,
                    {
                        "invoice_number": "FORGED-INV",
                        field: value,
                    },
                    content_type="application/json",
                )

                self.assertEqual(
                    response.status_code, 400, response.content
                )

        self.assertFalse(
            Invoice.objects.filter(
                invoice_number="FORGED-INV"
            ).exists()
        )

    def test_blank_invoice_number_rejected(self):
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.URL,
            {"invoice_number": "   "},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_forged_hospital_header_cannot_change_invoice_owner(self):
        self.client.force_login(self.user_a)

        response = self.client.post(
            self.URL,
            {"invoice_number": "HEADER-INV-A"},
            content_type="application/json",
            HTTP_X_HOSPITAL_ID=str(self.hospital_b.pk),
        )

        self.assertEqual(
            response.status_code, 201, response.content
        )

        invoice = Invoice.objects.get(
            invoice_number="HEADER-INV-A"
        )

        self.assertEqual(
            invoice.hospital_id, self.hospital_a.pk
        )
