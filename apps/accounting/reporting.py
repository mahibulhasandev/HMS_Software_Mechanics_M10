
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum

from .models import Transaction


def get_cash_flow_summary(
    *,
    hospital_id,
    start_date,
    end_date,
):
    """
    Calculate hospital cash flow using the transaction ledger.

    Dates are inclusive.

    Reversal transactions are not yet supported.
    If any exist in the requested period, reject
    the report rather than return misleading totals.
    """

    # 1. Validate dates.
    for value in (start_date, end_date):
        if (
            not isinstance(value, date)
            or isinstance(value, datetime)
        ):
            raise ValidationError(
                "Start date and end date must be date objects."
            )

    if start_date > end_date:
        raise ValidationError(
            "Start date cannot be after end date."
        )

    # 2. Only read this hospital's ledger.
    entries = Transaction.objects.filter(
        hospital_id=hospital_id,
        transaction_date__range=(
            start_date,
            end_date,
        ),
    )

    # 3. Aggregate all transaction types.
    totals = entries.aggregate(
        income=Sum(
            "amount",
            filter=Q(transaction_type="income"),
        ),
        expenses=Sum(
            "amount",
            filter=Q(transaction_type="expense"),
        ),
        refunds=Sum(
            "amount",
            filter=Q(transaction_type="refund"),
        ),
        reversal_count=Count(
            "id",
            filter=Q(transaction_type="reversal"),
        ),
    )

    # 4. Do not silently ignore reversals.
    if totals["reversal_count"]:
        raise ValidationError(
            "This period contains reversal transactions. "
            "Reversal-aware reporting is not yet implemented."
        )

    zero = Decimal("0.00")

    income = totals["income"] or zero
    expenses = totals["expenses"] or zero
    refunds = totals["refunds"] or zero

    # 5. Calculate net cash flow.
    net_cash_flow = income - expenses - refunds

    return {
        "hospital_id": hospital_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_income": income,
        "total_expenses": expenses,
        "total_refunds": refunds,
        "net_cash_flow": net_cash_flow,
    }

# ============================================================
# ACCOUNT-WISE FINANCIAL SUMMARY
# ============================================================

def get_account_wise_summary(
    *,
    hospital_id,
    start_date,
    end_date,
):
    """
    Calculate account-wise cash flow using the ledger.

    Only accounts with transactions in the requested
    period are included.

    Reversal transactions are not yet supported.
    """
    # Reuse existing date validation and reversal protection.
    overall = get_cash_flow_summary(
        hospital_id=hospital_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Read only this hospital's ledger.
    entries = Transaction.objects.filter(
        hospital_id=hospital_id,
        transaction_date__range=(
            start_date,
            end_date,
        ),
    )

    # Group transactions by account.
    account_totals = (
        entries.values(
            "account_id",
            "account__name",
        )
        .annotate(
            income=Sum(
                "amount",
                filter=Q(transaction_type="income"),
            ),
            expenses=Sum(
                "amount",
                filter=Q(transaction_type="expense"),
            ),
            refunds=Sum(
                "amount",
                filter=Q(transaction_type="refund"),
            ),
        )
        .order_by("account__name", "account_id")
    )

    zero = Decimal("0.00")
    accounts = []

    for row in account_totals:
        income = row["income"] or zero
        expenses = row["expenses"] or zero
        refunds = row["refunds"] or zero

        net_cash_flow = income - expenses - refunds

        accounts.append({
            "account_id": row["account_id"],
            "account_name": row["account__name"],
            "total_income": income,
            "total_expenses": expenses,
            "total_refunds": refunds,
            "net_cash_flow": net_cash_flow,
        })

    return {
        "hospital_id": hospital_id,
        "start_date": start_date,
        "end_date": end_date,
        "accounts": accounts,
        "overall": {
            "total_income": overall["total_income"],
            "total_expenses": overall["total_expenses"],
            "total_refunds": overall["total_refunds"],
            "net_cash_flow": overall["net_cash_flow"],
        },
    }