import uuid

from django.utils import timezone
from .models import Account, Payment, Transaction
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from datetime import date, datetime
from decimal import DecimalException
from .models import Expense, ExpenseCategory

from .models import Invoice, InvoiceItemStatus
from .models import (
    Invoice,
    InvoiceItem,
    InvoiceItemStatus,
    InvoiceStatus,
)


@transaction.atomic
def recalculate_invoice_totals(invoice_id, hospital_id):
    """
    Recalculate invoice subtotal and total.

    Rules:
    1. Only the requested hospital's invoice is used.
    2. Only active invoice items are counted.
    3. Discount cannot exceed subtotal.
    4. Amount paid cannot exceed the recalculated total.
    5. Voided invoices cannot be recalculated.
    """

    # Lock invoice to protect concurrent calculations.
    invoice = (
        Invoice.objects
        .select_for_update()
        .get(
            id=invoice_id,
            hospital_id=hospital_id
        )
    )

    if invoice.status == "voided":
        raise ValidationError(
            "Cannot recalculate a voided invoice."
        )

    # Calculate subtotal from active invoice items.
    result = (
        invoice.items
        .filter(
            hospital_id=hospital_id,
            status=InvoiceItemStatus.ACTIVE
        )
        .aggregate(subtotal=Sum("line_total"))
    )

    subtotal = result["subtotal"] or Decimal("0.00")

    # Validate discount.
    if invoice.discount < Decimal("0.00"):
        raise ValidationError(
            "Discount cannot be negative."
        )

    if invoice.discount > subtotal:
        raise ValidationError(
            "Discount cannot exceed subtotal."
        )

    total = subtotal - invoice.discount

    # Protect against invalid paid amounts.
    if invoice.amount_paid > total:
        raise ValidationError(
            "Invoice total cannot be less than amount paid."
        )

    # Update only calculated fields.
    invoice.subtotal = subtotal
    invoice.total = total

    invoice.save(
        update_fields=["subtotal", "total"]
    )

    return invoice

@transaction.atomic
def add_invoice_item(
    *,
    invoice_id,
    hospital_id,
    department_id,
    description,
    quantity,
    unit_price,
):
    """
    Add a manual billing item to a draft invoice.

    The item is created and the invoice totals are
    recalculated within the same database transaction.
    """

    # Lock the invoice to prevent concurrent changes.
    invoice = (
        Invoice.objects
        .select_for_update()
        .get(
            id=invoice_id,
            hospital_id=hospital_id,
        )
    )

    # Only draft invoices can accept new items.
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError(
            "Items can only be added to draft invoices."
        )

    # Validate quantity.
    if type(quantity) is not int or quantity <= 0:
        raise ValidationError(
            "Quantity must be a positive integer."
        )

    # Validate unit price.
    try:
        price = Decimal(str(unit_price))
        valid_price = (
            price.is_finite()
            and price >= Decimal("0.00")
            and price == price.quantize(Decimal("0.01"))
        )
    except (ValueError, TypeError, ArithmeticError):
        valid_price = False

    if not valid_price:
        raise ValidationError(
            "Unit price must be a non-negative amount "
            "with at most two decimal places."
        )

    # Calculate line total.
    line_total = price * quantity

    if line_total > Decimal("9999999999.99"):
        raise ValidationError(
            "Line total exceeds the allowed amount."
        )

    # Validate description.
    if not isinstance(description, str) or not description.strip():
        raise ValidationError(
            "Item description is required."
        )

    # Create the invoice item.
    item = InvoiceItem.objects.create(
        hospital_id=hospital_id,
        invoice=invoice,
        department_id=department_id,
        description=description.strip(),
        quantity=quantity,
        unit_price=price,
        line_total=line_total,
        status=InvoiceItemStatus.ACTIVE,
    )

    # Update subtotal and total automatically.
    recalculate_invoice_totals(
        invoice_id=invoice.id,
        hospital_id=hospital_id,
    )

    return item

@transaction.atomic
def process_payment(
    *,
    payment_id,
    hospital_id,
    invoice_id,
    account_id,
    received_by_hospital_user_id,
    amount,
    method,
    reference_no,
):
    """
    Record a completed invoice payment.

    A stable payment_id must be reused for retries.
    Payment, invoice update and ledger entry are atomic.
    """

    # 1. Validate payment ID.
    try:
        payment_id = uuid.UUID(str(payment_id))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Invalid payment ID.")

    # 2. Validate payment amount.
    if isinstance(amount, (bool, float)):
        raise ValidationError(
            "Use a decimal string for payment amount."
        )

    try:
        payment_amount = Decimal(str(amount))

        if (
            not payment_amount.is_finite()
            or payment_amount <= Decimal("0.00")
            or payment_amount != payment_amount.quantize(
                Decimal("0.01")
            )
        ):
            raise ValidationError(
                "Payment must be positive with "
                "at most two decimal places."
            )

    except (ArithmeticError, ValueError, TypeError):
        raise ValidationError("Invalid payment amount.")

    # Respect actual database decimal limits.
    Payment._meta.get_field("amount").clean(
        payment_amount, None
    )
    Transaction._meta.get_field("amount").clean(
        payment_amount, None
    )

    # 3. Validate payment method.
    valid_methods = {
        value
        for value, _ in Payment._meta.get_field(
            "method"
        ).choices
    }

    if method not in valid_methods:
        raise ValidationError("Invalid payment method.")

    if (
        not isinstance(reference_no, str)
        or not reference_no.strip()
    ):
        raise ValidationError(
            "Payment reference number is required."
        )

    reference_no = reference_no.strip()

    # 4. Lock invoice for concurrent payment safety.
    invoice = (
        Invoice.objects
        .select_for_update()
        .get(
            id=invoice_id,
            hospital_id=hospital_id,
        )
    )

    # 5. Handle retry using the same payment_id.
    existing = Payment.objects.filter(
        id=payment_id,
        hospital_id=hospital_id,
    ).first()

    if existing is not None:
        same_request = (
            existing.invoice_id == invoice.id
            and str(existing.account_id) == str(account_id)
            and existing.amount == payment_amount
            and existing.method == method
            and existing.reference_no == reference_no
            and str(
                existing.received_by_hospital_user_id
            ) == str(received_by_hospital_user_id)
            and existing.kind == "payment"
            and existing.status == "completed"
        )

        ledger_exists = Transaction.objects.filter(
            hospital_id=hospital_id,
            payment=existing,
            transaction_type="income",
        ).exists()

        if not same_request or not ledger_exists:
            raise ValidationError(
                "Payment ID already used or payment "
                "record is inconsistent."
            )

        return existing

    # 6. Check invoice status.
    if invoice.status not in (
        "issued",
        "partially_paid",
    ):
        raise ValidationError(
            "Only issued or partially paid "
            "invoices can receive payments."
        )

    # 7. Verify destination account.
    account = (
        Account.objects
        .select_for_update()
        .get(
            id=account_id,
            hospital_id=hospital_id,
            is_active=True,
        )
    )

    # Prevent reuse of a reference on this invoice.
    if Payment.objects.filter(
        hospital_id=hospital_id,
        invoice=invoice,
        reference_no=reference_no,
        kind="payment",
    ).exists():
        raise ValidationError(
            "Payment reference already used "
            "for this invoice."
        )

    # 8. Prevent overpayment.
    remaining_due = invoice.total - invoice.amount_paid

    if remaining_due <= Decimal("0.00"):
        raise ValidationError(
            "Invoice has no remaining balance."
        )

    if payment_amount > remaining_due:
        raise ValidationError(
            "Payment exceeds remaining balance."
        )

    # 9. Create payment record.
    now = timezone.now()

    payment = Payment.objects.create(
        id=payment_id,
        hospital_id=hospital_id,
        invoice=invoice,
        account=account,
        received_by_hospital_user_id=(
            received_by_hospital_user_id
        ),
        refunded_payment=None,
        amount=payment_amount,
        method=method,
        kind="payment",
        status="completed",
        reference_no=reference_no,
        paid_at=now,
    )

    # 10. Update invoice.
    invoice.amount_paid += payment_amount

    if invoice.amount_paid == invoice.total:
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"

    invoice.save(
        update_fields=["amount_paid", "status"]
    )

    # 11. Create append-only ledger entry.
    Transaction.objects.create(
        hospital_id=hospital_id,
        account=account,
        payment=payment,
        transaction_type="income",
        amount=payment_amount,
        transaction_date=timezone.localdate(now),
        description=(
            f"Payment received for invoice "
            f"{invoice.invoice_number}"
        ),
    )

    return payment

# ============================================================
# INVOICE LIFECYCLE SERVICES
# ============================================================

@transaction.atomic
def issue_invoice(*, invoice_id, hospital_id):
    """
    Issue a draft invoice after recalculating its totals.
    """

    invoice = (
        Invoice.objects
        .select_for_update()
        .get(
            id=invoice_id,
            hospital_id=hospital_id,
        )
    )

    # Only draft invoices can be issued.
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError(
            "Only draft invoices can be issued."
        )

    # Invoice must contain at least one active item.
    has_active_items = invoice.items.filter(
        hospital_id=hospital_id,
        status=InvoiceItemStatus.ACTIVE,
    ).exists()

    if not has_active_items:
        raise ValidationError(
            "Cannot issue an invoice without active items."
        )

    # Draft invoices must not contain payments.
    if (
        invoice.amount_paid != Decimal("0.00")
        or Payment.objects.filter(
            hospital_id=hospital_id,
            invoice=invoice,
        ).exists()
    ):
        raise ValidationError(
            "Cannot issue an invoice with payment history."
        )

    # Recalculate subtotal and total.
    invoice = recalculate_invoice_totals(
        invoice_id=invoice.id,
        hospital_id=hospital_id,
    )

    # Change status and record issue time.
    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()

    invoice.save(
        update_fields=["status", "issued_at"]
    )

    return invoice


@transaction.atomic
def void_invoice(*, invoice_id, hospital_id):
    """
    Void an unpaid draft or issued invoice.

    Preserve the original invoice and its items
    for audit purposes.
    """

    invoice = (
        Invoice.objects
        .select_for_update()
        .get(
            id=invoice_id,
            hospital_id=hospital_id,
        )
    )

    # Paid and partially paid invoices cannot be voided.
    if invoice.status not in (
        InvoiceStatus.DRAFT,
        InvoiceStatus.ISSUED,
    ):
        raise ValidationError(
            "Only draft or issued invoices can be voided."
        )

    # Reject invoices with any payment history.
    has_payments = Payment.objects.filter(
        hospital_id=hospital_id,
        invoice=invoice,
    ).exists()

    if has_payments or invoice.amount_paid != Decimal("0.00"):
        raise ValidationError(
            "Cannot void an invoice with payment history."
        )

    invoice.status = InvoiceStatus.VOIDED

    invoice.save(update_fields=["status"])

    return invoice

# ============================================================
# REFUND PROCESSING SERVICE
# ============================================================

@transaction.atomic
def process_refund(
    *,
    refund_id,
    hospital_id,
    original_payment_id,
    received_by_hospital_user_id,
    amount,
    method,
    reference_no,
):
    """
    Record a completed refund against an original payment.

    A stable refund_id must be reused for retries.
    Refund, invoice update, and ledger entry are atomic.
    """

    # 1. Validate refund ID.
    try:
        refund_id = uuid.UUID(str(refund_id))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Invalid refund ID.")

    # 2. Validate amount.
    if isinstance(amount, (bool, float)):
        raise ValidationError(
            "Use a decimal string for refund amount."
        )

    try:
        refund_amount = Decimal(str(amount))

        if (
            not refund_amount.is_finite()
            or refund_amount <= Decimal("0.00")
            or refund_amount != refund_amount.quantize(
                Decimal("0.01")
            )
        ):
            raise ValidationError(
                "Refund amount must be positive "
                "with at most two decimal places."
            )

    except (ArithmeticError, ValueError, TypeError):
        raise ValidationError("Invalid refund amount.")

    Payment._meta.get_field("amount").clean(
        refund_amount, None
    )
    Transaction._meta.get_field("amount").clean(
        refund_amount, None
    )

    # 3. Validate refund method and reference.
    valid_methods = {
        value
        for value, _ in Payment._meta.get_field(
            "method"
        ).choices
    }

    if method not in valid_methods:
        raise ValidationError("Invalid refund method.")

    if (
        not isinstance(reference_no, str)
        or not reference_no.strip()
    ):
        raise ValidationError(
            "Refund reference number is required."
        )

    reference_no = reference_no.strip()

    # 4. Locate original payment.
    original = Payment.objects.get(
        id=original_payment_id,
        hospital_id=hospital_id,
    )

    # 5. Lock invoice first to serialize financial updates.
    invoice = (
        Invoice.objects
        .select_for_update()
        .get(
            id=original.invoice_id,
            hospital_id=hospital_id,
        )
    )

    original = (
        Payment.objects
        .select_for_update()
        .get(
            id=original_payment_id,
            hospital_id=hospital_id,
            invoice=invoice,
        )
    )

    # 6. Safely handle retry with the same refund ID.
    existing = Payment.objects.filter(
        id=refund_id,
        hospital_id=hospital_id,
    ).first()

    if existing is not None:
        same_request = (
            existing.refunded_payment_id == original.id
            and existing.invoice_id == invoice.id
            and existing.account_id == original.account_id
            and existing.amount == refund_amount
            and existing.method == method
            and existing.reference_no == reference_no
            and str(
                existing.received_by_hospital_user_id
            ) == str(received_by_hospital_user_id)
            and existing.kind == "refund"
            and existing.status == "completed"
        )

        ledger_exists = Transaction.objects.filter(
            hospital_id=hospital_id,
            payment=existing,
            account_id=original.account_id,
            amount=refund_amount,
            transaction_type="refund",
        ).exists()

        if not same_request or not ledger_exists:
            raise ValidationError(
                "Refund ID already used or refund "
                "record is inconsistent."
            )

        return existing

    # 7. Only completed original payments can be refunded.
    if (
        original.kind != "payment"
        or original.status != "completed"
    ):
        raise ValidationError(
            "Only completed payments can be refunded."
        )

    # Original income must exist in the ledger.
    original_ledger_exists = Transaction.objects.filter(
        hospital_id=hospital_id,
        payment=original,
        account_id=original.account_id,
        amount=original.amount,
        transaction_type="income",
    ).exists()

    if not original_ledger_exists:
        raise ValidationError(
            "Original payment ledger entry is missing "
            "or inconsistent."
        )

    # Refund only from the original active account.
    account = Account.objects.filter(
        id=original.account_id,
        hospital_id=hospital_id,
        is_active=True,
    ).first()

    if account is None:
        raise ValidationError(
            "Original payment account is not active."
        )

    # 8. Check invoice status.
    if invoice.status not in (
        "paid",
        "partially_paid",
    ):
        raise ValidationError(
            "Invoice is not eligible for a refund."
        )

    # 9. Prevent duplicate refund references.
    if Payment.objects.filter(
        hospital_id=hospital_id,
        invoice=invoice,
        kind="refund",
        reference_no=reference_no,
    ).exists():
        raise ValidationError(
            "Refund reference already used "
            "for this invoice."
        )

    # 10. Calculate how much was already refunded.
    previous_refunds = Payment.objects.filter(
        hospital_id=hospital_id,
        refunded_payment=original,
        kind="refund",
        status="completed",
    ).aggregate(total=Sum("amount"))["total"]

    already_refunded = (
        previous_refunds or Decimal("0.00")
    )

    refundable_balance = (
        original.amount - already_refunded
    )

    if (
        refund_amount > refundable_balance
        or refund_amount > invoice.amount_paid
    ):
        raise ValidationError(
            "Refund exceeds available refundable balance."
        )

    # 11. Create refund payment record.
    now = timezone.now()

    refund = Payment.objects.create(
        id=refund_id,
        hospital_id=hospital_id,
        invoice=invoice,
        account=account,
        received_by_hospital_user_id=(
            received_by_hospital_user_id
        ),
        refunded_payment=original,
        amount=refund_amount,
        method=method,
        kind="refund",
        status="completed",
        reference_no=reference_no,
        paid_at=now,
    )

    # 12. Reduce net paid amount.
    invoice.amount_paid -= refund_amount

    if invoice.amount_paid == Decimal("0.00"):
        invoice.status = "issued"
    else:
        invoice.status = "partially_paid"

    invoice.save(
        update_fields=["amount_paid", "status"]
    )

    # 13. Add a new append-only refund ledger entry.
    Transaction.objects.create(
        hospital_id=hospital_id,
        account=account,
        payment=refund,
        transaction_type="refund",
        amount=refund_amount,
        transaction_date=timezone.localdate(now),
        description=(
            f"Refund for invoice "
            f"{invoice.invoice_number}; "
            f"original payment {original.id}"
        ),
    )

    return refund

# ============================================================
# EXPENSE CREATION SERVICE
# ============================================================

@transaction.atomic
def create_expense(
    *,
    hospital_id,
    expense_category_id,
    account_id,
    amount,
    description,
    expense_date=None,
    supplier_id=None,
):
    """
    Create a draft hospital expense.

    Does not create a ledger entry.
    Payment and approval are separate operations.
    """

    # 1. Validate expense amount.
    if isinstance(amount, (bool, float)):
        raise ValidationError(
            "Use a decimal string for expense amount."
        )

    try:
        expense_amount = Decimal(str(amount))

        if (
            not expense_amount.is_finite()
            or expense_amount <= Decimal("0.00")
            or expense_amount != expense_amount.quantize(
                Decimal("0.01")
            )
        ):
            raise ValidationError(
                "Expense amount must be positive "
                "with at most two decimal places."
            )

    except (DecimalException, ValueError, TypeError):
        raise ValidationError("Invalid expense amount.")

    # Check the model's decimal limits.
    Expense._meta.get_field("amount").clean(
        expense_amount, None
    )

    # 2. Validate description.
    if (
        not isinstance(description, str)
        or not description.strip()
    ):
        raise ValidationError(
            "Expense description is required."
        )

    description = description.strip()

    # 3. Validate expense date.
    if expense_date is None:
        expense_date = timezone.localdate()

    if (
        not isinstance(expense_date, date)
        or isinstance(expense_date, datetime)
    ):
        raise ValidationError(
            "Expense date must be a date object."
        )

    # 4. Verify expense category belongs to hospital.
    category = ExpenseCategory.objects.get(
        id=expense_category_id,
        hospital_id=hospital_id,
    )

    # 5. Verify account belongs to hospital and is active.
    account = Account.objects.get(
        id=account_id,
        hospital_id=hospital_id,
        is_active=True,
    )

    # 6. Create draft expense.
    expense = Expense.objects.create(
        hospital_id=hospital_id,
        expense_category=category,
        account=account,
        supplier_id=supplier_id,
        approved_by_hospital_user_id=None,
        amount=expense_amount,
        expense_date=expense_date,
        description=description,
        status="draft",
    )

    return expense

# ============================================================
# EXPENSE APPROVAL WORKFLOW
# ============================================================

@transaction.atomic
def submit_expense_for_approval(
    *,
    expense_id,
    hospital_id,
):
    """
    Submit a draft expense for approval.

    Only draft expenses can be submitted.
    No payment or ledger entry is created.
    """

    # Lock expense to prevent concurrent status changes.
    expense = (
        Expense.objects
        .select_for_update()
        .get(
            id=expense_id,
            hospital_id=hospital_id,
        )
    )

    # Only draft expenses can be submitted.
    if expense.status != "draft":
        raise ValidationError(
            "Only draft expenses can be submitted."
        )

    # Ensure amount remains valid.
    if expense.amount <= Decimal("0.00"):
        raise ValidationError(
            "Expense amount must be positive."
        )

    # Verify the account is still active.
    account_exists = Account.objects.filter(
        id=expense.account_id,
        hospital_id=hospital_id,
        is_active=True,
    ).exists()

    if not account_exists:
        raise ValidationError(
            "Expense account is not active "
            "or does not belong to the hospital."
        )

    # Verify expense category belongs to the hospital.
    category_exists = ExpenseCategory.objects.filter(
        id=expense.expense_category_id,
        hospital_id=hospital_id,
    ).exists()

    if not category_exists:
        raise ValidationError(
            "Expense category does not belong "
            "to this hospital."
        )

    # Submit expense for approval.
    expense.status = "pending_approval"

    expense.save(
        update_fields=["status"]
    )

    return expense

# ============================================================
# EXPENSE APPROVAL AND REJECTION
# ============================================================

@transaction.atomic
def approve_expense(
    *,
    expense_id,
    hospital_id,
    approved_by_hospital_user_id,
):
    """
    Approve an expense awaiting approval.

    The approver's identity and permission must be
    verified by the calling authentication layer.
    """

    expense = (
        Expense.objects
        .select_for_update()
        .get(
            id=expense_id,
            hospital_id=hospital_id,
        )
    )

    # Only pending expenses can be approved.
    if expense.status != "pending_approval":
        raise ValidationError(
            "Only pending expenses can be approved."
        )

    # Validate the approver ID format.
    try:
        approver_id = uuid.UUID(
            str(approved_by_hospital_user_id)
        )
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(
            "A valid approver ID is required."
        )

    # Validate expense before approval.
    if expense.amount <= Decimal("0.00"):
        raise ValidationError(
            "Expense amount must be positive."
        )

    if not expense.description.strip():
        raise ValidationError(
            "Expense description is required."
        )

    # Check that the account is still active.
    if not Account.objects.filter(
        id=expense.account_id,
        hospital_id=hospital_id,
        is_active=True,
    ).exists():
        raise ValidationError(
            "Expense account is inactive or invalid."
        )

    # Verify category belongs to the same hospital.
    if not ExpenseCategory.objects.filter(
        id=expense.expense_category_id,
        hospital_id=hospital_id,
    ).exists():
        raise ValidationError(
            "Expense category is invalid."
        )

    # Approve expense.
    expense.status = "approved"
    expense.approved_by_hospital_user_id = approver_id

    expense.save(
        update_fields=[
            "status",
            "approved_by_hospital_user_id",
        ]
    )

    return expense


@transaction.atomic
def reject_expense(
    *,
    expense_id,
    hospital_id,
):
    """
    Reject an expense awaiting approval.

    The expense remains stored for audit purposes.
    """

    expense = (
        Expense.objects
        .select_for_update()
        .get(
            id=expense_id,
            hospital_id=hospital_id,
        )
    )

    # Only pending expenses can be rejected.
    if expense.status != "pending_approval":
        raise ValidationError(
            "Only pending expenses can be rejected."
        )

    expense.status = "rejected"

    expense.save(
        update_fields=["status"]
    )

    return expense