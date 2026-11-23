import uuid

from django.utils import timezone
from .models import Account, Payment, Transaction
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

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