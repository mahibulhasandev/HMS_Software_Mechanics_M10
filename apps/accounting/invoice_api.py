from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice, InvoiceStatus
from .permissions import AccountingRolePermission


class InvoiceCreateSerializer(serializers.Serializer):
    invoice_number = serializers.CharField(
        max_length=100,
        allow_blank=False,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)

        if unexpected:
            raise serializers.ValidationError({
                "unexpected_fields": sorted(unexpected)
            })

        return attrs


class InvoiceListAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get(self, request):
        hospital_id = request.accounting_hospital_id

        invoices = list(
            Invoice.objects.filter(
                hospital_id=hospital_id
            )
            .order_by("-issued_at", "-id")
            .values(
                "id",
                "invoice_number",
                "patient_id",
                "patient_visit_id",
                "subtotal",
                "discount",
                "total",
                "amount_paid",
                "status",
                "issued_at",
            )[:100]
        )

        return Response({
            "hospital_id": str(hospital_id),
            "invoices": invoices,
        })

    def post(self, request):
        serializer = InvoiceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        actor_uuid = getattr(
            request, "accounting_actor_uuid", None
        )

        if actor_uuid is None:
            raise PermissionDenied(
                "Accounting creator identity is unavailable."
            )

        invoice = Invoice.objects.create(
            hospital_id=request.accounting_hospital_id,
            created_by_hospital_user_id=actor_uuid,
            invoice_number=serializer.validated_data[
                "invoice_number"
            ],
            subtotal=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            status=InvoiceStatus.DRAFT,
            issued_at=timezone.now(),
        )

        return Response(
            {
                "hospital_id": str(
                    request.accounting_hospital_id
                ),
                "invoice": {
                    "id": str(invoice.pk),
                    "invoice_number": invoice.invoice_number,
                    "status": invoice.status,
                    "total": str(invoice.total),
                },
            },
            status=status.HTTP_201_CREATED,
        )
