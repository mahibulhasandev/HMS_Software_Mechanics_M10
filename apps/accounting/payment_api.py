from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, Invoice, Payment
from .permissions import AccountingRolePermission
from .services import process_payment, process_refund


class StrictFinancialSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    method = serializers.ChoiceField(
        choices=Payment._meta.get_field("method").choices
    )
    reference_no = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
    )

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
                "amount": "Use a decimal string, not a float or boolean."
            })

        return attrs


class PaymentInputSerializer(StrictFinancialSerializer):
    payment_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    account_id = serializers.UUIDField()


class RefundInputSerializer(StrictFinancialSerializer):
    refund_id = serializers.UUIDField()
    original_payment_id = serializers.UUIDField()


def execute_financial_service(service, **kwargs):
    try:
        return service(**kwargs)

    except (
        Invoice.DoesNotExist,
        Account.DoesNotExist,
        Payment.DoesNotExist,
    ) as exc:
        raise NotFound(
            "Financial record not found in your hospital."
        ) from exc

    except DjangoValidationError as exc:
        raise serializers.ValidationError({
            "detail": exc.messages
        }) from exc


class FinancialWriteAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get_actor_uuid(self, request):
        actor_uuid = getattr(
            request, "accounting_actor_uuid", None
        )

        if actor_uuid is None:
            raise PermissionDenied(
                "Accounting actor identity unavailable."
            )

        return actor_uuid

    def payment_response(self, request, payment):
        return Response(
            {
                "hospital_id": str(
                    request.accounting_hospital_id
                ),
                "payment": {
                    "id": str(payment.id),
                    "invoice_id": str(payment.invoice_id),
                    "account_id": str(payment.account_id),
                    "kind": payment.kind,
                    "status": payment.status,
                    "amount": str(payment.amount),
                    "method": payment.method,
                    "reference_no": payment.reference_no,
                    "paid_at": payment.paid_at,
                },
            },
            status=status.HTTP_200_OK,
        )


class PaymentCreateAPIView(FinancialWriteAPIView):
    def post(self, request):
        serializer = PaymentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = execute_financial_service(
            process_payment,
            hospital_id=request.accounting_hospital_id,
            received_by_hospital_user_id=self.get_actor_uuid(
                request
            ),
            **serializer.validated_data,
        )

        return self.payment_response(request, payment)


class RefundCreateAPIView(FinancialWriteAPIView):
    def post(self, request):
        serializer = RefundInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refund = execute_financial_service(
            process_refund,
            hospital_id=request.accounting_hospital_id,
            received_by_hospital_user_id=self.get_actor_uuid(
                request
            ),
            **serializer.validated_data,
        )

        return self.payment_response(request, refund)
