
import uuid
from django.db import models


# ============================================================
# BASE MODEL
# ============================================================

class HospitalOwnedModel(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    hospital_id = models.UUIDField()

    class Meta:
        abstract = True


# ============================================================
# 1. ACCOUNT
# ============================================================

class AccountType(models.TextChoices):
    CASH = "cash", "Cash"
    BANK = "bank", "Bank"
    MOBILE_WALLET = "mobile_wallet", "Mobile Wallet"
    CARD_SETTLEMENT = "card_settlement", "Card Settlement"
    PETTY_CASH = "petty_cash", "Petty Cash"


class Account(HospitalOwnedModel):
    name = models.TextField()
    account_type = models.TextField(choices=AccountType.choices)
    account_number = models.TextField()
    opening_balance = models.DecimalField(
        max_digits=14, decimal_places=2
    )
    is_active = models.BooleanField()

    class Meta:
        db_table = "accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_accounts_hospital_id_id"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    account_type__in=AccountType.values
                ),
                name="ck_accounts_type_valid"
            ),
        ]

    def __str__(self):
        return self.name


# ============================================================
# 2. INCOME CATEGORY
# ============================================================

class IncomeCategory(HospitalOwnedModel):
    department_id = models.UUIDField(null=True, blank=True)
    name = models.TextField()

    class Meta:
        db_table = "income_categories"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_income_cat_hospital_id"
            ),
        ]

    def __str__(self):
        return self.name


# ============================================================
# 3. EXPENSE CATEGORY
# ============================================================

class ExpenseCategory(HospitalOwnedModel):
    name = models.TextField()

    class Meta:
        db_table = "expense_categories"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_exp_cat_hospital_id"
            ),
            models.UniqueConstraint(
                fields=["hospital_id", "name"],
                name="uq_exp_cat_hospital_name"
            ),
        ]

    def __str__(self):
        return self.name


# ============================================================
# 4. INVOICE
# ============================================================

class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Paid"
    VOIDED = "voided", "Voided"


class InvoiceItemStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    VOIDED = "voided", "Voided"


class Invoice(HospitalOwnedModel):
    patient_id = models.UUIDField(
        null=True, blank=True, db_index=True
    )
    patient_visit_id = models.UUIDField(
        null=True, blank=True, db_index=True
    )
    created_by_hospital_user_id = models.UUIDField(
        db_index=True
    )

    invoice_number = models.TextField()

    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    status = models.TextField(
        choices=InvoiceStatus.choices
    )
    issued_at = models.DateTimeField()

    class Meta:
        db_table = "invoices"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_invoice_hospital_id"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=InvoiceStatus.values
                ),
                name="ck_invoice_status_valid"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(subtotal__gte=0)
                    & models.Q(discount__gte=0)
                    & models.Q(total__gte=0)
                    & models.Q(amount_paid__gte=0)
                ),
                name="ck_invoice_amounts_nonnegative"
            ),
        ]

    def __str__(self):
        return self.invoice_number


# ============================================================
# 5. INVOICE ITEM
# ============================================================

class InvoiceItem(HospitalOwnedModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        db_column="invoice_id",
        db_constraint=False,
        related_name="items"
    )

    department_id = models.UUIDField(db_index=True)

    appointment_id = models.UUIDField(
        null=True, blank=True
    )
    test_order_item_id = models.UUIDField(
        null=True, blank=True
    )
    medicine_sale_item_id = models.UUIDField(
        null=True, blank=True
    )
    blood_issue_id = models.UUIDField(
        null=True, blank=True
    )
    emergency_case_id = models.UUIDField(
        null=True, blank=True, db_index=True
    )

    description = models.TextField()
    quantity = models.IntegerField()

    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    status = models.TextField(
        choices=InvoiceItemStatus.choices
    )

    class Meta:
        db_table = "invoice_items"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_inv_item_hospital_id"
            ),

            # At most one source may be non-NULL.
            models.CheckConstraint(
                condition=(
                    ~(
                        models.Q(appointment_id__isnull=False)
                        & models.Q(test_order_item_id__isnull=False)
                    )
                    & ~(
                        models.Q(appointment_id__isnull=False)
                        & models.Q(medicine_sale_item_id__isnull=False)
                    )
                    & ~(
                        models.Q(appointment_id__isnull=False)
                        & models.Q(blood_issue_id__isnull=False)
                    )
                    & ~(
                        models.Q(appointment_id__isnull=False)
                        & models.Q(emergency_case_id__isnull=False)
                    )
                    & ~(
                        models.Q(test_order_item_id__isnull=False)
                        & models.Q(medicine_sale_item_id__isnull=False)
                    )
                    & ~(
                        models.Q(test_order_item_id__isnull=False)
                        & models.Q(blood_issue_id__isnull=False)
                    )
                    & ~(
                        models.Q(test_order_item_id__isnull=False)
                        & models.Q(emergency_case_id__isnull=False)
                    )
                    & ~(
                        models.Q(medicine_sale_item_id__isnull=False)
                        & models.Q(blood_issue_id__isnull=False)
                    )
                    & ~(
                        models.Q(medicine_sale_item_id__isnull=False)
                        & models.Q(emergency_case_id__isnull=False)
                    )
                    & ~(
                        models.Q(blood_issue_id__isnull=False)
                        & models.Q(emergency_case_id__isnull=False)
                    )
                ),
                name="ck_invoice_item_one_source"
            ),

            # Previously missing status constraint.
            models.CheckConstraint(
                condition=models.Q(
                    status__in=InvoiceItemStatus.values
                ),
                name="ck_inv_item_status_valid"
            ),

            models.UniqueConstraint(
                fields=["hospital_id", "appointment_id"],
                condition=(
                    models.Q(appointment_id__isnull=False)
                    & ~models.Q(
                        status=InvoiceItemStatus.VOIDED
                    )
                ),
                name="uq_inv_item_appt_active"
            ),

            models.UniqueConstraint(
                fields=["hospital_id", "test_order_item_id"],
                condition=(
                    models.Q(test_order_item_id__isnull=False)
                    & ~models.Q(
                        status=InvoiceItemStatus.VOIDED
                    )
                ),
                name="uq_inv_item_test_active"
            ),

            models.UniqueConstraint(
                fields=["hospital_id", "medicine_sale_item_id"],
                condition=(
                    models.Q(medicine_sale_item_id__isnull=False)
                    & ~models.Q(
                        status=InvoiceItemStatus.VOIDED
                    )
                ),
                name="uq_inv_item_medicine_active"
            ),

            models.UniqueConstraint(
                fields=["hospital_id", "blood_issue_id"],
                condition=(
                    models.Q(blood_issue_id__isnull=False)
                    & ~models.Q(
                        status=InvoiceItemStatus.VOIDED
                    )
                ),
                name="uq_inv_item_blood_active"
            ),

            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="ck_invoice_item_quantity_positive"
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(unit_price__gte=0)
                    & models.Q(line_total__gte=0)
                ),
                name="ck_invoice_item_amounts_nonnegative"
            ),
        ]

    def __str__(self):
        return self.description


# ============================================================
# 6. PAYMENT
# ============================================================

class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    MOBILE_WALLET = "mobile_wallet", "Mobile Wallet"
    CHEQUE = "cheque", "Cheque"
    OTHER = "other", "Other"


class PaymentKind(models.TextChoices):
    PAYMENT = "payment", "Payment"
    REFUND = "refund", "Refund"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    VOIDED = "voided", "Voided"


class Payment(HospitalOwnedModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="invoice_id",
        related_name="payments"
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="account_id",
        related_name="payments"
    )

    received_by_hospital_user_id = models.UUIDField()

    refunded_payment = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="refunded_payment_id",
        related_name="refunds"
    )

    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    method = models.TextField(
        choices=PaymentMethod.choices
    )
    kind = models.TextField(
        choices=PaymentKind.choices
    )
    status = models.TextField(
        choices=PaymentStatus.choices
    )

    reference_no = models.TextField()
    paid_at = models.DateTimeField()

    class Meta:
        db_table = "payments"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_payment_hospital_id"
            ),

            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ck_payment_amount_positive"
            ),

            models.CheckConstraint(
                condition=models.Q(
                    method__in=PaymentMethod.values
                ),
                name="ck_payment_method_valid"
            ),

            models.CheckConstraint(
                condition=models.Q(
                    kind__in=PaymentKind.values
                ),
                name="ck_payment_kind_valid"
            ),

            models.CheckConstraint(
                condition=models.Q(
                    status__in=PaymentStatus.values
                ),
                name="ck_payment_status_valid"
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind=PaymentKind.REFUND,
                        refunded_payment__isnull=False
                    )
                    | models.Q(
                        kind=PaymentKind.PAYMENT,
                        refunded_payment__isnull=True
                    )
                ),
                name="ck_payment_refund_reference"
            ),
        ]

    def __str__(self):
        return f"{self.kind}: {self.amount}"


# ============================================================
# 7. EXPENSE
# ============================================================

class ExpenseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    APPROVED = "approved", "Approved"
    PAID = "paid", "Paid"
    REJECTED = "rejected", "Rejected"


class Expense(HospitalOwnedModel):
    expense_category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="expense_category_id",
        related_name="expenses"
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="account_id",
        related_name="expenses"
    )

    supplier_id = models.UUIDField(
        null=True, blank=True
    )
    approved_by_hospital_user_id = models.UUIDField(
        null=True, blank=True
    )

    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    expense_date = models.DateField()
    description = models.TextField()
    status = models.TextField(
        choices=ExpenseStatus.choices
    )

    class Meta:
        db_table = "expenses"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_expense_hospital_id"
            ),

            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ck_expense_amount_positive"
            ),

            models.CheckConstraint(
                condition=models.Q(
                    status__in=ExpenseStatus.values
                ),
                name="ck_expense_status_valid"
            ),
        ]

    def __str__(self):
        return f"{self.description}: {self.amount}"


# ============================================================
# 8. TRANSACTION
# ============================================================

class TransactionType(models.TextChoices):
    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"
    REFUND = "refund", "Refund"
    REVERSAL = "reversal", "Reversal"


class Transaction(HospitalOwnedModel):
    # Append-only enforcement will require database protection.

    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="account_id",
        related_name="transactions"
    )

    income_category = models.ForeignKey(
        IncomeCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="income_category_id",
        related_name="transactions"
    )

    expense_category = models.ForeignKey(
        ExpenseCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="expense_category_id",
        related_name="transactions"
    )

    payment = models.OneToOneField(
        Payment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="payment_id",
        related_name="ledger_transaction"
    )

    expense = models.OneToOneField(
        Expense,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="expense_id",
        related_name="ledger_transaction"
    )

    reversed_transaction = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        db_column="reversed_transaction_id",
        related_name="reversal_entry"
    )

    transaction_type = models.TextField(
        choices=TransactionType.choices
    )

    amount = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    transaction_date = models.DateField()
    description = models.TextField()

    class Meta:
        db_table = "transactions"
        constraints = [
            models.UniqueConstraint(
                fields=["hospital_id", "id"],
                name="uq_transaction_hospital_id"
            ),

            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ck_transaction_amount_positive"
            ),

            models.CheckConstraint(
                condition=models.Q(
                    transaction_type__in=TransactionType.values
                ),
                name="ck_transaction_type_valid"
            ),

            models.CheckConstraint(
                condition=(
                    (
                        models.Q(payment__isnull=False)
                        & models.Q(expense__isnull=True)
                        & models.Q(reversed_transaction__isnull=True)
                    )
                    | (
                        models.Q(payment__isnull=True)
                        & models.Q(expense__isnull=False)
                        & models.Q(reversed_transaction__isnull=True)
                    )
                    | (
                        models.Q(payment__isnull=True)
                        & models.Q(expense__isnull=True)
                        & models.Q(reversed_transaction__isnull=False)
                    )
                ),
                name="ck_transaction_one_origin"
            ),

            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            transaction_type__in=[
                                TransactionType.INCOME,
                                TransactionType.REFUND
                            ]
                        )
                        & models.Q(payment__isnull=False)
                    )
                    | (
                        models.Q(
                            transaction_type=TransactionType.EXPENSE
                        )
                        & models.Q(expense__isnull=False)
                    )
                    | (
                        models.Q(
                            transaction_type=TransactionType.REVERSAL
                        )
                        & models.Q(reversed_transaction__isnull=False)
                    )
                ),
                name="ck_transaction_type_origin"
            ),
        ]

    def __str__(self):
        return f"{self.transaction_type}: {self.amount}"
