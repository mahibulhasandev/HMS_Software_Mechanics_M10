import hashlib
import json


from rest_framework.pagination import LimitOffsetPagination
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from .permissions import AccountingRolePermission

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from rest_framework import serializers, status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
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


class ExpenseIdempotencyConflict(APIException):

    status_code = 409

    default_detail = (
        "Idempotency key already used for a different request."
    )

    default_code = "idempotency_conflict"


def expense_request_fingerprint(actor_uuid, payload):

    expense_date = payload.get("expense_date")

    canonical = {
        "version": 1,
        "actor_uuid": str(actor_uuid),
        "expense_category_id": str(
            payload["expense_category_id"]
        ),
        "account_id": str(payload["account_id"]),
        "amount": format(payload["amount"], ".2f"),
        "description": payload["description"].strip(),
        "expense_date": (
            expense_date.isoformat()
            if expense_date is not None
            else None
        ),
    }

    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def expense_replay_response(expense, fingerprint):

    if expense.request_fingerprint != fingerprint:

        raise ExpenseIdempotencyConflict()

    return Response(
        expense_response(expense),
        status=status.HTTP_200_OK,
        headers={
            "Idempotency-Replayed": "true",
        },
    )


class ExpenseCreateAPIView(FinancialWriteAPIView):

    def get(self, request):
        return ExpenseListAPIView().get(request)


    def post(self, request):

        actor_uuid = self.get_actor_uuid(request)

        serializer = ExpenseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = serializer.validated_data

        hospital_id = request.accounting_hospital_id

        raw_key = request.headers.get("Idempotency-Key")

        # Preserve compatibility with existing API clients.

        if raw_key is None:

            expense = execute_expense_service(
                create_expense,
                hospital_id=hospital_id,
                **payload,
            )

            return Response(
                expense_response(expense),
                status=status.HTTP_201_CREATED,
            )

        try:

            key = serializers.UUIDField().run_validation(
                raw_key
            )

        except serializers.ValidationError as exc:

            raise serializers.ValidationError({
                "Idempotency-Key": "A valid UUID is required."
            }) from exc

        fingerprint = expense_request_fingerprint(
            actor_uuid,
            payload,
        )

        existing = Expense.objects.filter(
            hospital_id=hospital_id,
            idempotency_key=key,
        ).first()

        if existing is not None:

            return expense_replay_response(
                existing,
                fingerprint,
            )

        try:

            expense = execute_expense_service(
                create_expense,
                hospital_id=hospital_id,
                idempotency_key=key,
                request_fingerprint=fingerprint,
                **payload,
            )

        except IntegrityError as exc:

            # Handle only the known idempotency constraint.
            # The failed insert has already been rolled back
            # by execute_expense_service's atomic block.

            cause = getattr(exc, "__cause__", None)

            diag = getattr(cause, "diag", None)

            constraint = getattr(
                diag,
                "constraint_name",
                None,
            )

            if constraint != "uq_expense_hospital_idem_key":

                raise

            existing = Expense.objects.filter(
                hospital_id=hospital_id,
                idempotency_key=key,
            ).first()

            if existing is None:

                raise

            return expense_replay_response(
                existing,
                fingerprint,
            )

        return Response(
            expense_response(expense),
            status=status.HTTP_201_CREATED,
            headers={
                "Idempotency-Replayed": "false",
            },
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


# EXPENSE READ API

class ExpensePagination(LimitOffsetPagination):

    default_limit = 50
    max_limit = 100


class ExpenseListAPIView(APIView):

    authentication_classes = [SessionAuthentication]

    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get(self, request):

        hospital_id = request.accounting_hospital_id

        expenses = Expense.objects.filter(
            hospital_id=hospital_id
        ).order_by("-expense_date", "-id")

        selected_status = request.query_params.get("status")

        if selected_status is not None:

            valid_statuses = {
                value for value, label in
                Expense._meta.get_field("status").flatchoices
            }

            if selected_status not in valid_statuses:
                raise serializers.ValidationError({
                    "status": "Invalid expense status."
                })

            expenses = expenses.filter(
                status=selected_status
            )

        paginator = ExpensePagination()

        page = paginator.paginate_queryset(
            expenses, request, view=self
        )

        return Response({
            "hospital_id": str(hospital_id),
            "count": paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "expenses": [
                expense_response(expense)["expense"]
                for expense in page
            ],
        })


class ExpenseDetailAPIView(APIView):

    authentication_classes = [SessionAuthentication]

    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get(self, request, expense_id):

        expense = Expense.objects.filter(
            id=expense_id,
            hospital_id=request.accounting_hospital_id,
        ).first()

        if expense is None:
            raise NotFound(
                "Expense not found in your hospital."
            )

        return Response(
            expense_response(expense)
        )
