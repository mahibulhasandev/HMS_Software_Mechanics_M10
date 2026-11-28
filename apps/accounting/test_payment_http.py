from apps.accounting._test_helpers import create_test_user
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import (
    Account, AccountingMembership, Invoice,
    InvoiceStatus, Payment, Transaction,
)
from apps.hospitals.models import Hospital


class PaymentRefundHTTPTests(TestCase):
    PAYMENT_URL = "/api/accounting/payments/"
    REFUND_URL = "/api/accounting/refunds/"

    @classmethod
    def setUpTestData(cls):
        with connection.cursor() as cursor:
            cursor.execute("GRANT USAGE ON SCHEMA public TO hms_app")
            cursor.execute("GRANT SELECT, UPDATE ON accounts TO hms_app")
            cursor.execute(
                "GRANT SELECT, UPDATE ON invoices TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT, INSERT, UPDATE ON payments TO hms_app"
            )
            cursor.execute(
                "GRANT SELECT, INSERT ON transactions TO hms_app"
            )

        User = get_user_model()

        cls.user_a = create_test_user(email='payment_user_a@example.test')
        cls.user_b = create_test_user(email='payment_user_b@example.test')
        cls.staff = create_test_user(email='payment_staff@example.test')
        cls.no_membership = create_test_user(
            email='payment_no_membership@example.test'
        )

        cls.hospital_a = Hospital.objects.create(
            name="Payment Hospital A",
            registration_number="PAY-HOSP-A",
            address="Address A",
            phone="100001",
            email="paymenta@example.com",
            timezone="Asia/Dhaka",
        )
        cls.hospital_b = Hospital.objects.create(
            name="Payment Hospital B",
            registration_number="PAY-HOSP-B",
            address="Address B",
            phone="100002",
            email="paymentb@example.com",
            timezone="Asia/Dhaka",
        )

        for user, hospital, role in (
            (cls.user_a, cls.hospital_a, "accountant"),
            (cls.user_b, cls.hospital_b, "accountant"),
            (cls.staff, cls.hospital_a, "staff"),
        ):
            AccountingMembership.objects.create(
                user=user, hospital=hospital,
                role=role, is_active=True,
            )

        cls.account_a = Account.objects.create(
            hospital_id=cls.hospital_a.pk,
            name="Payment Cash A",
            account_type="cash",
            account_number="PAY-ACC-A",
            opening_balance=0,
            is_active=True,
        )
        cls.account_b = Account.objects.create(
            hospital_id=cls.hospital_b.pk,
            name="Payment Cash B",
            account_type="cash",
            account_number="PAY-ACC-B",
            opening_balance=0,
            is_active=True,
        )

        cls.invoice_a = Invoice.objects.create(
            hospital_id=cls.hospital_a.pk,
            created_by_hospital_user_id=uuid4(),
            invoice_number="PAY-INV-A",
            subtotal=Decimal("100.00"),
            discount=Decimal("0.00"),
            total=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status=InvoiceStatus.ISSUED,
            issued_at=timezone.now(),
        )
        cls.invoice_b = Invoice.objects.create(
            hospital_id=cls.hospital_b.pk,
            created_by_hospital_user_id=uuid4(),
            invoice_number="PAY-INV-B",
            subtotal=Decimal("80.00"),
            discount=Decimal("0.00"),
            total=Decimal("80.00"),
            amount_paid=Decimal("0.00"),
            status=InvoiceStatus.ISSUED,
            issued_at=timezone.now(),
        )

    def payment_data(self, **changes):
        data = {
            "payment_id": str(uuid4()),
            "invoice_id": str(self.invoice_a.pk),
            "account_id": str(self.account_a.pk),
            "amount": "100.00",
            "method": "cash",
            "reference_no": "PAY-REF-001",
        }
        data.update(changes)
        return data

    def refund_data(self, original_id, **changes):
        data = {
            "refund_id": str(uuid4()),
            "original_payment_id": str(original_id),
            "amount": "25.00",
            "method": "cash",
            "reference_no": "REFUND-REF-001",
        }
        data.update(changes)
        return data

    def submit(self, url, user, data):
        self.client.force_login(user)
        return self.client.post(
            url, data, content_type="application/json"
        )

    def test_payment_marks_invoice_paid_and_adds_ledger(self):
        response = self.submit(
            self.PAYMENT_URL, self.user_a, self.payment_data()
        )
        self.assertEqual(response.status_code, 200, response.content)

        payment = Payment.objects.get(
            pk=response.json()["payment"]["id"]
        )
        membership = AccountingMembership.objects.get(user=self.user_a)

        self.assertEqual(payment.hospital_id, self.hospital_a.pk)
        self.assertEqual(
            payment.received_by_hospital_user_id,
            membership.actor_uuid,
        )
        self.assertEqual(payment.kind, "payment")
        self.assertEqual(payment.status, "completed")

        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.amount_paid, Decimal("100.00"))
        self.assertEqual(self.invoice_a.status, InvoiceStatus.PAID)

        ledger = Transaction.objects.get(payment=payment)
        self.assertEqual(ledger.transaction_type, "income")
        self.assertEqual(ledger.amount, Decimal("100.00"))

    def test_partial_payment(self):
        response = self.submit(
            self.PAYMENT_URL, self.user_a,
            self.payment_data(amount="40.00"),
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.amount_paid, Decimal("40.00"))
        self.assertEqual(
            self.invoice_a.status, InvoiceStatus.PARTIALLY_PAID
        )

    def test_payment_retry_is_idempotent(self):
        data = self.payment_data(amount="40.00")

        first = self.submit(self.PAYMENT_URL, self.user_a, data)
        second = self.submit(self.PAYMENT_URL, self.user_a, data)

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(
            first.json()["payment"]["id"],
            second.json()["payment"]["id"],
        )
        self.assertEqual(
            Payment.objects.filter(
                pk=data["payment_id"]
            ).count(), 1
        )
        self.assertEqual(
            Transaction.objects.filter(
                payment_id=data["payment_id"]
            ).count(), 1
        )

        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.amount_paid, Decimal("40.00"))

    def test_overpayment_rejected(self):
        response = self.submit(
            self.PAYMENT_URL, self.user_a,
            self.payment_data(amount="101.00"),
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Payment.objects.count(), 0)

    def test_refund_updates_invoice_and_ledger(self):
        payment_response = self.submit(
            self.PAYMENT_URL, self.user_a, self.payment_data()
        )
        self.assertEqual(payment_response.status_code, 200)

        original_id = payment_response.json()["payment"]["id"]

        refund_response = self.submit(
            self.REFUND_URL, self.user_a,
            self.refund_data(original_id),
        )
        self.assertEqual(
            refund_response.status_code, 200, refund_response.content
        )

        refund = Payment.objects.get(
            pk=refund_response.json()["payment"]["id"]
        )
        self.assertEqual(refund.kind, "refund")
        self.assertEqual(str(refund.refunded_payment_id), original_id)

        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.amount_paid, Decimal("75.00"))
        self.assertEqual(
            self.invoice_a.status, InvoiceStatus.PARTIALLY_PAID
        )

        ledger = Transaction.objects.get(payment=refund)
        self.assertEqual(ledger.transaction_type, "refund")
        self.assertEqual(ledger.amount, Decimal("25.00"))
        self.assertEqual(Transaction.objects.count(), 2)

    def test_refund_retry_idempotent(self):
        payment = self.submit(
            self.PAYMENT_URL, self.user_a, self.payment_data()
        )
        self.assertEqual(payment.status_code, 200)

        data = self.refund_data(payment.json()["payment"]["id"])

        first = self.submit(self.REFUND_URL, self.user_a, data)
        second = self.submit(self.REFUND_URL, self.user_a, data)

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(
            first.json()["payment"]["id"],
            second.json()["payment"]["id"],
        )
        self.assertEqual(Payment.objects.count(), 2)
        self.assertEqual(Transaction.objects.count(), 2)

        self.invoice_a.refresh_from_db()
        self.assertEqual(self.invoice_a.amount_paid, Decimal("75.00"))

    def test_refund_limit_rejected(self):
        payment = self.submit(
            self.PAYMENT_URL, self.user_a,
            self.payment_data(amount="35.00"),
        )
        self.assertEqual(payment.status_code, 200)

        response = self.submit(
            self.REFUND_URL, self.user_a,
            self.refund_data(
                payment.json()["payment"]["id"],
                amount="36.00",
            ),
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_cross_hospital_payment_denied(self):
        response = self.submit(
            self.PAYMENT_URL, self.user_a,
            self.payment_data(
                invoice_id=str(self.invoice_b.pk),
                account_id=str(self.account_b.pk),
                amount="20.00",
            ),
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(Payment.objects.count(), 0)

    def test_cross_hospital_refund_denied(self):
        other_payment = self.submit(
            self.PAYMENT_URL, self.user_b,
            self.payment_data(
                invoice_id=str(self.invoice_b.pk),
                account_id=str(self.account_b.pk),
                amount="80.00",
                reference_no="PAY-B-001",
            ),
        )
        self.assertEqual(
            other_payment.status_code, 200, other_payment.content
        )

        response = self.submit(
            self.REFUND_URL, self.user_a,
            self.refund_data(
                other_payment.json()["payment"]["id"]
            ),
        )
        self.assertEqual(response.status_code, 404, response.content)

        self.invoice_b.refresh_from_db()
        self.assertEqual(self.invoice_b.amount_paid, Decimal("80.00"))

    def test_staff_cannot_payment_or_refund(self):
        for url, data in (
            (self.PAYMENT_URL, self.payment_data()),
            (self.REFUND_URL, self.refund_data(uuid4())),
        ):
            with self.subTest(url=url):
                response = self.submit(url, self.staff, data)
                self.assertEqual(response.status_code, 403)

    def test_invalid_and_forged_fields_rejected(self):
        for change in (
            {"amount": "-5.00"},
            {"amount": "101.000"},
            {"method": "invalid_method"},
            {"hospital_id": str(self.hospital_b.pk)},
            {"received_by_hospital_user_id": str(uuid4())},
        ):
            with self.subTest(change=change):
                response = self.submit(
                    self.PAYMENT_URL, self.user_a,
                    self.payment_data(**change),
                )
                self.assertEqual(
                    response.status_code, 400, response.content
                )

        response = self.submit(
            self.REFUND_URL, self.user_a,
            self.refund_data(
                uuid4(),
                hospital_id=str(self.hospital_b.pk),
            ),
        )
        self.assertEqual(response.status_code, 400, response.content)

        self.assertEqual(Payment.objects.count(), 0)

    def test_anonymous_and_no_membership_denied(self):
        for url in (self.PAYMENT_URL, self.REFUND_URL):
            with self.subTest(url=url):
                self.client.logout()
                self.assertEqual(
                    self.client.post(
                        url, {}, content_type="application/json"
                    ).status_code,
                    401,
                )

                self.client.force_login(self.no_membership)
                self.assertEqual(
                    self.client.post(
                        url, {}, content_type="application/json"
                    ).status_code,
                    403,
                )
