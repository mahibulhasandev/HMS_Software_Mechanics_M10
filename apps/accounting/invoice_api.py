from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice
from .permissions import AccountingRolePermission


class InvoiceListAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, AccountingRolePermission]

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
