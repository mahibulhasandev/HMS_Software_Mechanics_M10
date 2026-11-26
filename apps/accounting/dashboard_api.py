from decimal import Decimal

from django.db.models import (
    Sum,
    Count,
    F,
    DecimalField,
)

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Invoice,
    Expense,
    Transaction,
)

from .permissions import AccountingRolePermission

from .balance_api import (
    accounts_with_balances,
    balance_response,
    InvalidLedgerError,
)

from .report_api import (
    FinancialReportFilterSerializer,
    report_aggregates,
    empty_totals,
    normalize_totals,
    format_totals,
    MONEY_FIELDS,
)

from .transaction_api import TransactionReadSerializer


ZERO = Decimal("0.00")

PREVIEW_LIMIT = 10


class DashboardFilterSerializer(
    FinancialReportFilterSerializer
):

    account_id = None
    group_by = None


def money_string(value):

    return format(
        value if value is not None else ZERO,
        ".2f",
    )


def dashboard_account_summary(hospital_id):

    queryset = accounts_with_balances(
        hospital_id
    )

    totals = queryset.aggregate(

        account_count=Count("pk"),

        total_opening=Sum(
            "opening_balance"
        ),

        total_movement=Sum(
            "net_movement"
        ),

        total_invalid=Sum(
            "invalid_ledger_count"
        ),
    )

    if totals["total_invalid"]:

        raise InvalidLedgerError()

    opening = totals["total_opening"] or ZERO

    movement = totals["total_movement"] or ZERO

    accounts = list(
        queryset.order_by(
            "name", "id"
        )[:PREVIEW_LIMIT]
    )

    return {

        "account_count": totals["account_count"],

        "total_opening_balance": money_string(
            opening
        ),

        "total_net_movement": money_string(
            movement
        ),

        "total_current_balance": money_string(
            opening + movement
        ),

        "accounts": [
            balance_response(account)
            for account in accounts
        ],

        "has_more_accounts": (
            totals["account_count"] > PREVIEW_LIMIT
        ),
    }


def dashboard_invoice_summary(hospital_id):

    money = DecimalField(
        max_digits=30,
        decimal_places=2,
    )

    queryset = Invoice.objects.filter(
        hospital_id=hospital_id,
        status__in=(
            "issued",
            "partially_paid",
        ),
        total__gt=F("amount_paid"),
    )

    totals = queryset.aggregate(

        outstanding_count=Count("pk"),

        outstanding_amount=Sum(
            F("total") - F("amount_paid"),
            output_field=money,
        ),
    )

    return {

        "outstanding_invoice_count": (
            totals["outstanding_count"]
        ),

        "outstanding_amount": money_string(
            totals["outstanding_amount"]
        ),
    }


def dashboard_expense_summary(hospital_id):

    pending = Expense.objects.filter(
        hospital_id=hospital_id,
        status="pending_approval",
    ).aggregate(

        pending_count=Count("pk"),

        pending_amount=Sum("amount"),
    )

    approved = Expense.objects.filter(
        hospital_id=hospital_id,
        status="approved",
    ).aggregate(

        approved_count=Count("pk"),

        approved_amount=Sum("amount"),
    )

    return {

        "pending_approval_count": (
            pending["pending_count"]
        ),

        "pending_approval_amount": money_string(
            pending["pending_amount"]
        ),

        "approved_unpaid_count": (
            approved["approved_count"]
        ),

        "approved_unpaid_amount": money_string(
            approved["approved_amount"]
        ),
    }


def dashboard_financial_summary(
    hospital_id,
    date_from,
    date_to,
):

    queryset = Transaction.objects.filter(
        hospital_id=hospital_id,
        transaction_date__gte=date_from,
        transaction_date__lte=date_to,
    ).order_by()

    rows = queryset.values(
        "transaction_date"
    ).annotate(
        **report_aggregates()
    ).order_by(
        "transaction_date"
    )

    totals = empty_totals()

    daily = []

    for row in rows:

        values = normalize_totals(row)

        for field in MONEY_FIELDS:

            totals[field] += values[field]

        totals["transaction_count"] += (
            values["transaction_count"]
        )

        entry = format_totals(values)

        entry["date"] = (
            row["transaction_date"].isoformat()
        )

        daily.append(entry)

    recent = queryset.order_by(
        "-transaction_date",
        "-id",
    )[:PREVIEW_LIMIT]

    return {

        "summary": format_totals(totals),

        "daily_movement": daily,

        "recent_transactions": (
            TransactionReadSerializer(
                recent,
                many=True,
            ).data
        ),
    }


class AccountingDashboardAPIView(APIView):

    authentication_classes = [
        SessionAuthentication
    ]

    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get(self, request):

        serializer = DashboardFilterSerializer(
            data=request.query_params
        )

        serializer.is_valid(
            raise_exception=True
        )

        filters = serializer.validated_data

        hospital_id = (
            request.accounting_hospital_id
        )

        date_from = filters["date_from"]

        date_to = filters["date_to"]

        return Response({

            "hospital_id": str(hospital_id),

            "period": {

                "date_from": date_from.isoformat(),

                "date_to": date_to.isoformat(),
            },

            "account_summary": (
                dashboard_account_summary(
                    hospital_id
                )
            ),

            "invoice_summary": (
                dashboard_invoice_summary(
                    hospital_id
                )
            ),

            "expense_summary": (
                dashboard_expense_summary(
                    hospital_id
                )
            ),

            "financial_summary": (
                dashboard_financial_summary(
                    hospital_id,
                    date_from,
                    date_to,
                )
            ),
        })
