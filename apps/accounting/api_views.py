from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account
from .permissions import AccountingRolePermission


class AccountListAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, AccountingRolePermission]

    def get(self, request):
        hospital_id = request.accounting_hospital_id

        accounts = list(
            Account.objects.filter(
                hospital_id=hospital_id
            ).order_by("name").values(
                "id",
                "name",
                "account_type",
                "account_number",
                "is_active",
            )
        )

        return Response({
            "hospital_id": str(hospital_id),
            "role": request.accounting_role,
            "accounts": accounts,
        })
