from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Transaction
from .permissions import AccountingRolePermission


class TransactionPagination(LimitOffsetPagination):

    default_limit = 50
    max_limit = 100


class TransactionReadSerializer(serializers.ModelSerializer):

    account_id = serializers.UUIDField(read_only=True)
    income_category_id = serializers.UUIDField(read_only=True)
    expense_category_id = serializers.UUIDField(read_only=True)
    payment_id = serializers.UUIDField(read_only=True)
    expense_id = serializers.UUIDField(read_only=True)
    reversed_transaction_id = serializers.UUIDField(read_only=True)

    class Meta:

        model = Transaction

        fields = (
            "id",
            "hospital_id",
            "account_id",
            "income_category_id",
            "expense_category_id",
            "payment_id",
            "expense_id",
            "reversed_transaction_id",
            "transaction_type",
            "amount",
            "transaction_date",
            "description",
        )

        read_only_fields = fields


class TransactionFilterSerializer(serializers.Serializer):

    transaction_type = serializers.ChoiceField(
        choices=Transaction._meta.get_field(
            "transaction_type"
        ).choices,
        required=False,
    )

    account_id = serializers.UUIDField(
        required=False
    )

    date_from = serializers.DateField(
        required=False
    )

    date_to = serializers.DateField(
        required=False
    )

    def validate(self, attrs):

        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if (
            date_from is not None
            and date_to is not None
            and date_from > date_to
        ):

            raise serializers.ValidationError({
                "date_to": (
                    "End date must be on or after start date."
                )
            })

        return attrs


class TransactionReadAPIView(APIView):

    authentication_classes = [
        SessionAuthentication
    ]

    permission_classes = [
        IsAuthenticated,
        AccountingRolePermission,
    ]

    def get_queryset(self, request):

        return Transaction.objects.filter(
            hospital_id=request.accounting_hospital_id
        )


class TransactionListAPIView(TransactionReadAPIView):

    def get(self, request):

        queryset = self.get_queryset(request)

        filter_serializer = TransactionFilterSerializer(
            data=request.query_params
        )

        filter_serializer.is_valid(
            raise_exception=True
        )

        filters = filter_serializer.validated_data

        if "transaction_type" in filters:

            queryset = queryset.filter(
                transaction_type=filters[
                    "transaction_type"
                ]
            )

        if "account_id" in filters:

            queryset = queryset.filter(
                account_id=filters["account_id"]
            )

        if "date_from" in filters:

            queryset = queryset.filter(
                transaction_date__gte=filters[
                    "date_from"
                ]
            )

        if "date_to" in filters:

            queryset = queryset.filter(
                transaction_date__lte=filters[
                    "date_to"
                ]
            )

        queryset = queryset.order_by(
            "-transaction_date",
            "-id",
        )

        paginator = TransactionPagination()

        page = paginator.paginate_queryset(
            queryset,
            request,
            view=self,
        )

        serializer = TransactionReadSerializer(
            page,
            many=True,
        )

        return Response({
            "hospital_id": str(
                request.accounting_hospital_id
            ),
            "count": paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "transactions": serializer.data,
        })


class TransactionDetailAPIView(TransactionReadAPIView):

    def get(self, request, transaction_id):

        ledger = self.get_queryset(request).filter(
            id=transaction_id
        ).first()

        if ledger is None:

            raise NotFound(
                "Transaction not found in your hospital."
            )

        serializer = TransactionReadSerializer(
            ledger
        )

        return Response({
            "hospital_id": str(
                request.accounting_hospital_id
            ),
            "transaction": serializer.data,
        })
