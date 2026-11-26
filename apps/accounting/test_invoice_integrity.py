from decimal import Decimal
from uuid import uuid4

from django.db import (
    connection,
    transaction,
    IntegrityError,
)
from django.test import TestCase
from django.utils import timezone

from apps.accounting.models import Invoice


class InvoiceFinancialIntegrityTests(TestCase):

    @classmethod
    def setUpTestData(cls):

        cls.hospital_id = uuid4()
        cls.actor_id = uuid4()

    def create_invoice(self, **overrides):

        data = {
            "hospital_id": self.hospital_id,
            "created_by_hospital_user_id": self.actor_id,
            "invoice_number": f"INT-{uuid4().hex}",
            "subtotal": Decimal("1000.00"),
            "discount": Decimal("100.00"),
            "total": Decimal("900.00"),
            "amount_paid": Decimal("0.00"),
            "status": "draft",
            "issued_at": timezone.now(),
        }

        data.update(overrides)

        return Invoice.objects.create(**data)

    def assert_database_rejection(
        self,
        operation,
        constraint,
    ):

        with self.assertRaises(IntegrityError) as caught:

            with transaction.atomic():

                operation()

        self.assertEqual(
            caught.exception.__cause__.diag.constraint_name,
            constraint,
        )

    # Test 1
    def test_valid_invoice_statuses(self):

        cases = (
            ("draft", "0.00"),
            ("issued", "0.00"),
            ("partially_paid", "400.00"),
            ("paid", "900.00"),
            ("voided", "0.00"),
        )

        for status, amount_paid in cases:

            with self.subTest(status=status):

                invoice = self.create_invoice(
                    status=status,
                    amount_paid=Decimal(amount_paid),
                )

                invoice.refresh_from_db()

                self.assertEqual(
                    invoice.status, status
                )

                self.assertEqual(
                    invoice.amount_paid,
                    Decimal(amount_paid),
                )

                self.assertEqual(
                    invoice.total,
                    Decimal("900.00"),
                )

        self.assertEqual(
            Invoice.objects.filter(
                hospital_id=self.hospital_id
            ).count(),
            5,
        )

    # Test 2
    def test_incorrect_total_rejected(self):

        self.assert_database_rejection(

            lambda: self.create_invoice(
                total=Decimal("950.00")
            ),

            "ck_invoice_total_calculation",
        )

        self.assertFalse(
            Invoice.objects.exists()
        )

    # Test 3
    def test_excessive_discount_rejected(self):

        self.assert_database_rejection(

            lambda: self.create_invoice(
                discount=Decimal("1200.00"),
                total=Decimal("0.00"),
            ),

            "ck_invoice_total_calculation",
        )

        self.assertFalse(
            Invoice.objects.exists()
        )

    # Test 4
    def test_overpayment_rejected(self):

        self.assert_database_rejection(

            lambda: self.create_invoice(
                status="paid",
                amount_paid=Decimal("1000.00"),
            ),

            "ck_invoice_payment_limit",
        )

        self.assertFalse(
            Invoice.objects.exists()
        )

    # Test 5
    def test_unpaid_status_with_payment_rejected(self):

        for status in (
            "draft",
            "issued",
            "voided",
        ):

            with self.subTest(status=status):

                self.assert_database_rejection(

                    lambda: self.create_invoice(
                        status=status,
                        amount_paid=Decimal("100.00"),
                    ),

                    "ck_invoice_payment_status",
                )

        self.assertFalse(
            Invoice.objects.exists()
        )

    # Test 6
    def test_paid_invoice_amount_mismatch_rejected(self):

        for amount in (
            "0.00",
            "400.00",
            "899.99",
        ):

            with self.subTest(amount=amount):

                self.assert_database_rejection(

                    lambda: self.create_invoice(
                        status="paid",
                        amount_paid=Decimal(amount),
                    ),

                    "ck_invoice_payment_status",
                )

    # Test 7
    def test_invalid_partial_payment_rejected(self):

        for amount in (
            "0.00",
            "900.00",
        ):

            with self.subTest(amount=amount):

                self.assert_database_rejection(

                    lambda: self.create_invoice(
                        status="partially_paid",
                        amount_paid=Decimal(amount),
                    ),

                    "ck_invoice_payment_status",
                )

    # Test 8
    def test_zero_value_invoice_allowed(self):

        for status in (
            "draft",
            "issued",
            "paid",
            "voided",
        ):

            with self.subTest(status=status):

                invoice = self.create_invoice(
                    subtotal=Decimal("1000.00"),
                    discount=Decimal("1000.00"),
                    total=Decimal("0.00"),
                    amount_paid=Decimal("0.00"),
                    status=status,
                )

                self.assertEqual(
                    invoice.total,
                    Decimal("0.00"),
                )

        self.assert_database_rejection(

            lambda: self.create_invoice(
                subtotal=Decimal("1000.00"),
                discount=Decimal("1000.00"),
                total=Decimal("0.00"),
                amount_paid=Decimal("0.00"),
                status="partially_paid",
            ),

            "ck_invoice_payment_status",
        )

    # Test 9
    def test_invalid_update_preserves_invoice(self):

        invoice = self.create_invoice(
            status="issued"
        )

        self.assert_database_rejection(

            lambda: Invoice.objects.filter(
                pk=invoice.pk
            ).update(
                total=Decimal("800.00")
            ),

            "ck_invoice_total_calculation",
        )

        self.assert_database_rejection(

            lambda: Invoice.objects.filter(
                pk=invoice.pk
            ).update(
                amount_paid=Decimal("100.00")
            ),

            "ck_invoice_payment_status",
        )

        invoice.refresh_from_db()

        self.assertEqual(
            invoice.total,
            Decimal("900.00"),
        )

        self.assertEqual(
            invoice.amount_paid,
            Decimal("0.00"),
        )

        self.assertEqual(
            invoice.status,
            "issued",
        )

        # A financially consistent update is allowed.

        Invoice.objects.filter(
            pk=invoice.pk
        ).update(
            amount_paid=Decimal("400.00"),
            status="partially_paid",
        )

        invoice.refresh_from_db()

        self.assertEqual(
            invoice.amount_paid,
            Decimal("400.00"),
        )

        self.assertEqual(
            invoice.status,
            "partially_paid",
        )

    # Test 10
    def test_restricted_role_cannot_bypass_constraints(self):

        invoice = self.create_invoice(
            status="issued"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                "GRANT USAGE ON SCHEMA public TO hms_app"
            )

            cursor.execute(
                "GRANT SELECT, UPDATE ON invoices TO hms_app"
            )

        with transaction.atomic():

            with connection.cursor() as cursor:

                cursor.execute(
                    "SET LOCAL ROLE hms_app"
                )

                cursor.execute(
                    "SELECT set_config("
                    "'app.hospital_id', %s, true)",
                    [str(self.hospital_id)],
                )

                cursor.execute(
                    "SELECT current_user"
                )

                self.assertEqual(
                    cursor.fetchone()[0],
                    "hms_app",
                )

            self.assertTrue(
                Invoice.objects.filter(
                    pk=invoice.pk
                ).exists()
            )

            self.assert_database_rejection(

                lambda: Invoice.objects.filter(
                    pk=invoice.pk
                ).update(
                    amount_paid=Decimal("100.00")
                ),

                "ck_invoice_payment_status",
            )

            self.assert_database_rejection(

                lambda: Invoice.objects.filter(
                    pk=invoice.pk
                ).update(
                    total=Decimal("950.00")
                ),

                "ck_invoice_total_calculation",
            )

            updated = Invoice.objects.filter(
                pk=invoice.pk
            ).update(
                amount_paid=Decimal("900.00"),
                status="paid",
            )

            self.assertEqual(updated, 1)

            # Restore role and transaction settings.

            transaction.set_rollback(True)

        invoice.refresh_from_db()

        self.assertEqual(
            invoice.status, "issued"
        )

        self.assertEqual(
            invoice.amount_paid,
            Decimal("0.00"),
        )
