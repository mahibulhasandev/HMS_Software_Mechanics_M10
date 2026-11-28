from decimal import Decimal

from django.db.models import (
    Sum,
    Count,
    Q,
    F,
    Case,
    When,
    UUIDField,
)

from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Transaction
from .permissions import AccountingRolePermission

from .balance_api import (
    ledger_expressions,
    InvalidLedgerError,
)


class FinancialReportFilterSerializer(serializers.Serializer):

    date_from = serializers.DateField()
    date_to = serializers.DateField()

    account_id = serializers.UUIDField(
        required=False
    )

    group_by = serializers.ChoiceField(
        choices=("summary", "date", "category"),
        default="summary",
        required=False,
    )

    def validate(self, attrs):

        start = attrs["date_from"]
        end = attrs["date_to"]

        if start > end:

            raise serializers.ValidationError({
                "date_to": "End date cannot precede start date."
            })

        if (end - start).days > 365:

            raise serializers.ValidationError({
                "date_to": "Maximum report period is 366 days."
            })

        return attrs


MONEY_FIELDS = (
    "income",
    "expense",
    "refund",
    "reversal_inflow",
    "reversal_outflow",
    "net_movement",
)


def report_aggregates():

    money, _, signed_amount, invalid_entry = ledger_expressions()

    return {

        "income": Sum(
            "amount",
            filter=Q(transaction_type="income"),
            output_field=money,
        ),

        "expense": Sum(
            "amount",
            filter=Q(transaction_type="expense"),
            output_field=money,
        ),

        "refund": Sum(
            "amount",
            filter=Q(transaction_type="refund"),
            output_field=money,
        ),

        "reversal_inflow": Sum(
            "amount",
            filter=Q(
                transaction_type="reversal",
                reversed_transaction__transaction_type__in=(
                    "expense",
                    "refund",
                ),
            ),
            output_field=money,
        ),

        "reversal_outflow": Sum(
            "amount",
            filter=Q(
                transaction_type="reversal",
                reversed_transaction__transaction_type="income",
            ),
            output_field=money,
        ),

        "net_movement": Sum(
            signed_amount,
            output_field=money,
        ),

        "transaction_count": Count("id"),

        "invalid_count": Sum(invalid_entry),
    }


def empty_totals():

    return {
        **{
            field: Decimal("0.00")
            for field in MONEY_FIELDS
        },
        "transaction_count": 0,
    }


def normalize_totals(row):

    if row.get("invalid_count"):

        raise InvalidLedgerError()

    return {
        **{
            field: row.get(field) or Decimal("0.00")
            for field in MONEY_FIELDS
        },
        "transaction_count": row.get(
            "transaction_count", 0
        ),
    }


def format_totals(totals):

    inflow = (
        totals["income"]
        + totals["reversal_inflow"]
    )

    outflow = (
        totals["expense"]
        + totals["refund"]
        + totals["reversal_outflow"]
    )

    return {
        **{
            field: format(totals[field], ".2f")
            for field in MONEY_FIELDS
        },

        "total_inflow": format(inflow, ".2f"),

        "total_outflow": format(outflow, ".2f"),

        "transaction_count": totals["transaction_count"],
    }


class FinancialSummaryAPIView(APIView):

    authentication_classes = [
        SessionAuthentication
    ]

    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get(self, request):

        serializer = FinancialReportFilterSerializer(
            data=request.query_params
        )

        serializer.is_valid(
            raise_exception=True
        )

        filters = serializer.validated_data

        hospital_id = request.accounting_hospital_id

        queryset = Transaction.objects.filter(
            hospital_id=hospital_id,
            transaction_date__gte=filters["date_from"],
            transaction_date__lte=filters["date_to"],
        ).order_by()

        if "account_id" in filters:

            queryset = queryset.filter(
                account_id=filters["account_id"]
            )

        group_by = filters["group_by"]

        aggregates = report_aggregates()

        breakdown = []

        if group_by == "summary":

            raw = queryset.aggregate(
                **aggregates
            )

            totals = normalize_totals(raw)

        else:

            if group_by == "date":

                grouped = queryset.values(
                    "transaction_date"
                ).annotate(
                    **aggregates
                ).order_by(
                    "transaction_date"
                )

            else:

                grouped = queryset.annotate(

                    report_income_category_id=Case(

                        When(
                            transaction_type="reversal",
                            then=F(
                                "reversed_transaction__income_category_id"
                            ),
                        ),

                        default=F("income_category_id"),
                        output_field=UUIDField(),
                    ),

                    report_expense_category_id=Case(

                        When(
                            transaction_type="reversal",
                            then=F(
                                "reversed_transaction__expense_category_id"
                            ),
                        ),

                        default=F("expense_category_id"),
                        output_field=UUIDField(),
                    ),

                ).values(
                    "report_income_category_id",
                    "report_expense_category_id",
                ).annotate(
                    **aggregates
                ).order_by(
                    "report_income_category_id",
                    "report_expense_category_id",
                )

            rows = list(grouped[:1001])

            if len(rows) > 1000:

                raise serializers.ValidationError({
                    "group_by": (
                        "Too many report groups. "
                        "Use a narrower date range or account filter."
                    )
                })

            totals = empty_totals()

            for row in rows:

                values = normalize_totals(row)

                for field in MONEY_FIELDS:

                    totals[field] += values[field]

                totals["transaction_count"] += (
                    values["transaction_count"]
                )

                entry = format_totals(values)

                if group_by == "date":

                    entry["date"] = (
                        row["transaction_date"].isoformat()
                    )

                else:

                    income_id = row[
                        "report_income_category_id"
                    ]

                    expense_id = row[
                        "report_expense_category_id"
                    ]

                    entry["income_category_id"] = (
                        str(income_id)
                        if income_id is not None
                        else None
                    )

                    entry["expense_category_id"] = (
                        str(expense_id)
                        if expense_id is not None
                        else None
                    )

                breakdown.append(entry)

        return Response({

            "hospital_id": str(hospital_id),

            "date_from": filters[
                "date_from"
            ].isoformat(),

            "date_to": filters[
                "date_to"
            ].isoformat(),

            "account_id": (
                str(filters["account_id"])
                if "account_id" in filters
                else None
            ),

            "group_by": group_by,

            "summary": format_totals(totals),

            "breakdown": breakdown,
        })
