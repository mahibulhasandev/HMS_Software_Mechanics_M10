from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum

from .models import Transaction


def get_cash_flow_summary(*, hospital_id, start_date, end_date):
    """Calculate hospital cash flow from its ledger for an inclusive date range.

    Only fully validated expense reversals are included. Other reversal types
    are rejected so that the report never silently produces misleading totals.
    """
    for value in (start_date, end_date):
        if not isinstance(value, date) or isinstance(value, datetime):
            raise ValidationError(
                "Start date and end date must be date objects."
            )

    if start_date > end_date:
        raise ValidationError(
            "Start date cannot be after end date."
        )

    entries = Transaction.objects.filter(
        hospital_id=hospital_id,
        transaction_date__range=(start_date, end_date),
    )

    expense_reversals = Decimal("0.00")
    reversals = entries.filter(
        transaction_type="reversal",
    ).select_related(
        "reversed_transaction__expense",
    )

    for reversal in reversals:
        original = reversal.reversed_transaction
        if original is None:
            raise ValidationError(
                "Unsupported or inconsistent reversal transaction."
            )

        original_expense = original.expense
        if (
            original.transaction_type != "expense"
            or original.expense_id is None
            or original_expense is None
            or original.hospital_id != reversal.hospital_id
            or original.account_id != reversal.account_id
            or original.expense_category_id != reversal.expense_category_id
            or original.amount != reversal.amount
            or original_expense.hospital_id != reversal.hospital_id
            or original_expense.status != "reversed"
            or original_expense.account_id != original.account_id
            or original_expense.expense_category_id
            != original.expense_category_id
            or original_expense.amount != original.amount
        ):
            raise ValidationError(
                "Unsupported or inconsistent reversal transaction."
            )

        expense_reversals += reversal.amount

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
    )

    zero = Decimal("0.00")
    income = totals["income"] or zero
    expenses = totals["expenses"] or zero
    refunds = totals["refunds"] or zero
    net_cash_flow = income - expenses - refunds + expense_reversals

    return {
        "hospital_id": hospital_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_income": income,
        "total_expenses": expenses,
        "total_refunds": refunds,
        "total_expense_reversals": expense_reversals,
        "net_cash_flow": net_cash_flow,
    }


def get_account_wise_summary(*, hospital_id, start_date, end_date):
    """Calculate account-wise cash flow for an inclusive date range.

    Only accounts with transactions in the requested period are included.
    The hospital-level summary validates all reversal entries before account
    aggregation is performed.
    """
    overall = get_cash_flow_summary(
        hospital_id=hospital_id,
        start_date=start_date,
        end_date=end_date,
    )

    entries = Transaction.objects.filter(
        hospital_id=hospital_id,
        transaction_date__range=(start_date, end_date),
    )

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
            expense_reversals=Sum(
                "amount",
                filter=Q(transaction_type="reversal"),
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
        expense_reversals = row["expense_reversals"] or zero
        net_cash_flow = income - expenses - refunds + expense_reversals

        accounts.append({
            "account_id": row["account_id"],
            "account_name": row["account__name"],
            "total_income": income,
            "total_expenses": expenses,
            "total_refunds": refunds,
            "total_expense_reversals": expense_reversals,
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
            "total_expense_reversals": overall["total_expense_reversals"],
            "net_cash_flow": overall["net_cash_flow"],
        },
    }
