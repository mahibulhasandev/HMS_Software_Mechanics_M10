
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