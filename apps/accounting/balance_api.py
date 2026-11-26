from decimal import Decimal

from django.db.models import (
    Case,
    When,
    Value,
    F,
    Q,
    Sum,
    OuterRef,
    Subquery,
    DecimalField,
    IntegerField,
)

from django.db.models.functions import Coalesce

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.exceptions import NotFound, APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, Transaction
from .permissions import AccountingRolePermission


class InvalidLedgerError(APIException):

    status_code = 409
    default_detail = "Account contains an inconsistent ledger entry."
    default_code = "invalid_ledger"


class BalancePagination(LimitOffsetPagination):

    default_limit = 50
    max_limit = 100


def accounts_with_balances(hospital_id):

    money = DecimalField(
        max_digits=30,
        decimal_places=2,
    )

    zero = Value(
        Decimal("0.00"),
        output_field=money,
    )

    valid_reversal = Q(
        transaction_type="reversal",
        reversed_transaction__hospital_id=F("hospital_id"),
        reversed_transaction__account_id=F("account_id"),
        reversed_transaction__amount=F("amount"),
        reversed_transaction__transaction_type__in=(
            "income",
            "expense",
            "refund",
        ),
    )

    signed_amount = Case(

        When(
            transaction_type="income",
            then=F("amount"),
        ),

        When(
            transaction_type__in=("expense", "refund"),
            then=-F("amount"),
        ),

        When(
            valid_reversal & Q(
                reversed_transaction__transaction_type__in=(
                    "expense",
                    "refund",
                )
            ),
            then=F("amount"),
        ),

        When(
            valid_reversal & Q(
                reversed_transaction__transaction_type="income"
            ),
            then=-F("amount"),
        ),

        default=zero,
        output_field=money,
    )

    invalid_entry = Case(

        When(
            transaction_type__in=(
                "income",
                "expense",
                "refund",
            ),
            then=Value(0),
        ),

        When(
            valid_reversal,
            then=Value(0),
        ),

        default=Value(1),
        output_field=IntegerField(),
    )

    ledger = Transaction.objects.filter(
        hospital_id=hospital_id,
        account_id=OuterRef("pk"),
    ).order_by().values("account_id")

    net_movement = ledger.annotate(
        total=Sum(
            signed_amount,
            output_field=money,
        )
    ).values("total")

    invalid_count = ledger.annotate(
        total=Sum(invalid_entry)
    ).values("total")

    return Account.objects.filter(
        hospital_id=hospital_id
    ).annotate(

        net_movement=Coalesce(
            Subquery(
                net_movement,
                output_field=money,
            ),
            zero,
            output_field=money,
        ),

        invalid_ledger_count=Coalesce(
            Subquery(
                invalid_count,
                output_field=IntegerField(),
            ),
            Value(0),
        ),

    )


def balance_response(account):

    if account.invalid_ledger_count:
        raise InvalidLedgerError()

    current_balance = (
        account.opening_balance
        + account.net_movement
    )

    return {
        "id": str(account.pk),
        "name": account.name,
        "account_type": account.account_type,
        "account_number": account.account_number,
        "is_active": account.is_active,

        "opening_balance": format(
            account.opening_balance, ".2f"
        ),

        "net_movement": format(
            account.net_movement, ".2f"
        ),

        "current_balance": format(
            current_balance, ".2f"
        ),
    }


class BalanceReadAPIView(APIView):

    authentication_classes = [
        SessionAuthentication
    ]

    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]


class AccountBalanceListAPIView(BalanceReadAPIView):

    def get(self, request):

        hospital_id = request.accounting_hospital_id

        queryset = accounts_with_balances(
            hospital_id
        ).order_by("name", "id")

        paginator = BalancePagination()

        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        return Response({
            "hospital_id": str(hospital_id),
            "count": paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),

            "accounts": [
                balance_response(account)
                for account in page
            ],
        })


class AccountBalanceDetailAPIView(BalanceReadAPIView):

    def get(self, request, account_id):

        hospital_id = request.accounting_hospital_id

        account = accounts_with_balances(
            hospital_id
        ).filter(
            pk=account_id
        ).first()

        if account is None:

            raise NotFound(
                "Account not found in your hospital."
            )

        return Response({
            "hospital_id": str(hospital_id),
            "account": balance_response(account),
        })
