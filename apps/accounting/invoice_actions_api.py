from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice
from .permissions import AccountingRolePermission
from .services import add_invoice_item, issue_invoice, void_invoice


class InvoiceItemInputSerializer(serializers.Serializer):
    department_id = serializers.UUIDField()
    description = serializers.CharField(allow_blank=False)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)

        if unexpected:
            raise serializers.ValidationError({
                "unexpected_fields": sorted(unexpected)
            })

        return attrs


def call_invoice_service(service, **kwargs):
    try:
        return service(**kwargs)
    except Invoice.DoesNotExist as exc:
        raise NotFound(
            "Invoice not found in your hospital."
        ) from exc
    except DjangoValidationError as exc:
        raise serializers.ValidationError({
            "detail": exc.messages
        }) from exc


class InvoiceWriteAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]


class InvoiceItemCreateAPIView(InvoiceWriteAPIView):

    def post(self, request, invoice_id):
        serializer = InvoiceItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item = call_invoice_service(
            add_invoice_item,
            invoice_id=invoice_id,
            hospital_id=request.accounting_hospital_id,
            **serializer.validated_data,
        )

        return Response(
            {
                "hospital_id": str(request.accounting_hospital_id),
                "item": {
                    "id": str(item.id),
                    "invoice_id": str(item.invoice_id),
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "line_total": str(item.line_total),
                    "status": item.status,
                },
            },
            status=status.HTTP_201_CREATED,
        )


def invoice_action_response(request, invoice_id, service):
    if request.data:
        raise serializers.ValidationError({
            "detail": "No request body fields are accepted."
        })

    invoice = call_invoice_service(
        service,
        invoice_id=invoice_id,
        hospital_id=request.accounting_hospital_id,
    )

    return Response({
        "hospital_id": str(request.accounting_hospital_id),
        "invoice": {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "subtotal": str(invoice.subtotal),
            "total": str(invoice.total),
            "amount_paid": str(invoice.amount_paid),
        },
    })


class InvoiceIssueAPIView(InvoiceWriteAPIView):

    def post(self, request, invoice_id):
        return invoice_action_response(
            request, invoice_id, issue_invoice
        )


class InvoiceVoidAPIView(InvoiceWriteAPIView):

    def post(self, request, invoice_id):
        return invoice_action_response(
            request, invoice_id, void_invoice
        )
