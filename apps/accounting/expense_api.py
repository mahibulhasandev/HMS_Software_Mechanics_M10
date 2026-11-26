from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from .models import (
    Account,
    Expense,
    ExpenseCategory,
    AccountingMembership,
)

from .payment_api import FinancialWriteAPIView

from .services import (
    create_expense,
    submit_expense_for_approval,
    approve_expense,
    reject_expense,
    pay_expense,
    reverse_paid_expense,
)


class StrictExpenseSerializer(serializers.Serializer):

    def validate(self, attrs):

        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError(
                "Expected a JSON object."
            )

        unexpected = set(self.initial_data) - set(self.fields)

        if unexpected:
            raise serializers.ValidationError({
                "unexpected_fields": sorted(unexpected)
            })

        if isinstance(
            self.initial_data.get("amount"), (float, bool)
        ):
            raise serializers.ValidationError({
                "amount": "Use a decimal string."
            })

        return attrs


amount_field = Expense._meta.get_field("amount")


class ExpenseCreateSerializer(StrictExpenseSerializer):

    expense_category_id = serializers.UUIDField()
    account_id = serializers.UUIDField()

    amount = serializers.DecimalField(
        max_digits=amount_field.max_digits,
        decimal_places=amount_field.decimal_places,
        min_value=Decimal("0.01"),
    )

    description = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )

    expense_date = serializers.DateField(required=False)


class ExpenseActionSerializer(StrictExpenseSerializer):
    pass


class ExpensePaySerializer(StrictExpenseSerializer):

    payment_confirmed = serializers.BooleanField()

    def validate(self, attrs):

        attrs = super().validate(attrs)

        if self.initial_data.get("payment_confirmed") is not True:
            raise serializers.ValidationError({
                "payment_confirmed": "Confirm completed payment."
            })

        return attrs


class ExpenseReverseSerializer(StrictExpenseSerializer):

    return_confirmed = serializers.BooleanField()

    return_reference = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )

    reason = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )

    def validate(self, attrs):

        attrs = super().validate(attrs)

        if self.initial_data.get("return_confirmed") is not True:
            raise serializers.ValidationError({
                "return_confirmed": "Confirm actual return of funds."
            })

        return attrs


def execute_expense_service(service, **kwargs):

    try:
        with transaction.atomic():
            return service(**kwargs)

    except (
        Expense.DoesNotExist,
        Account.DoesNotExist,
        ExpenseCategory.DoesNotExist,
    ) as exc:

        raise NotFound(
            "Financial record not found in your hospital."
        ) from exc

    except DjangoValidationError as exc:

        raise serializers.ValidationError({
            "detail": exc.messages
        }) from exc


def expense_response(expense, ledger=None):

    data = {
        "hospital_id": str(expense.hospital_id),
        "expense": {
            "id": str(expense.id),
            "expense_category_id": str(expense.expense_category_id),
            "account_id": str(expense.account_id),
            "amount": str(expense.amount),
            "description": expense.description,
            "expense_date": expense.expense_date,
            "status": expense.status,
            "approved_by_hospital_user_id": (
                str(expense.approved_by_hospital_user_id)
                if expense.approved_by_hospital_user_id
                else None
            ),
        },
    }

    if ledger is not None:

        data["transaction"] = {
            "id": str(ledger.id),
            "transaction_type": ledger.transaction_type,
            "amount": str(ledger.amount),
        }

    return data


class ExpenseCreateAPIView(FinancialWriteAPIView):

    def post(self, request):

        self.get_actor_uuid(request)

        serializer = ExpenseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        expense = execute_expense_service(
            create_expense,
            hospital_id=request.accounting_hospital_id,
            **serializer.validated_data,
        )

        return Response(
            expense_response(expense),
            status=status.HTTP_201_CREATED,
        )


class ExpenseActionAPIView(FinancialWriteAPIView):

    action = None

    def post(self, request, expense_id):

        hospital_id = request.accounting_hospital_id
        actor_uuid = self.get_actor_uuid(request)

        if self.action in {"approve", "reject", "reverse"}:

            if request.accounting_role != AccountingMembership.Role.ADMIN:

                raise PermissionDenied(
                    "Only hospital accounting administrators "
                    "can perform this action."
                )

        serializer_class = {
            "submit": ExpenseActionSerializer,
            "approve": ExpenseActionSerializer,
            "reject": ExpenseActionSerializer,
            "pay": ExpensePaySerializer,
            "reverse": ExpenseReverseSerializer,
        }.get(self.action)

        if serializer_class is None:
            raise NotFound("Unknown expense action.")

        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not Expense.objects.filter(
            id=expense_id,
            hospital_id=hospital_id,
        ).exists():

            raise NotFound(
                "Expense not found in your hospital."
            )

        kwargs = {
            "expense_id": expense_id,
            "hospital_id": hospital_id,
        }

        ledger = None

        if self.action == "submit":

            expense = execute_expense_service(
                submit_expense_for_approval,
                **kwargs,
            )

        elif self.action == "approve":

            expense = execute_expense_service(
                approve_expense,
                approved_by_hospital_user_id=actor_uuid,
                **kwargs,
            )

        elif self.action == "reject":

            expense = execute_expense_service(
                reject_expense,
                **kwargs,
            )

        elif self.action == "pay":

            ledger = execute_expense_service(
                pay_expense,
                **kwargs,
            )

        elif self.action == "reverse":

            ledger = execute_expense_service(
                reverse_paid_expense,
                return_reference=serializer.validated_data[
                    "return_reference"
                ],
                reason=serializer.validated_data["reason"],
                **kwargs,
            )

        if ledger is not None:

            expense = Expense.objects.get(
                id=expense_id,
                hospital_id=hospital_id,
            )

        return Response(
            expense_response(expense, ledger),
            status=status.HTTP_200_OK,
        )
