from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account
from .permissions import AccountingRolePermission
from .serializers import AccountCreateSerializer


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


    def post(self, request):
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account = serializer.save(
            hospital_id=request.accounting_hospital_id
        )

        return Response(
            {
                "hospital_id": str(request.accounting_hospital_id),
                "account": AccountCreateSerializer(account).data,
            },
            status=status.HTTP_201_CREATED,
        )
