from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IncomeCategory, ExpenseCategory
from .permissions import AccountingRolePermission


class HospitalCategorySerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        if any(
            key in self.initial_data
            for key in ("hospital_id", "hospital")
        ):
            raise serializers.ValidationError({
                "hospital_id": "Hospital is determined by your membership."
            })
        return attrs


class IncomeCategorySerializer(HospitalCategorySerializer):
    class Meta:
        model = IncomeCategory
        fields = ["id", "name", "department_id"]
        read_only_fields = ["id"]


class ExpenseCategorySerializer(HospitalCategorySerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        hospital_id = self.context["request"].accounting_hospital_id

        if ExpenseCategory.objects.filter(
            hospital_id=hospital_id,
            name=value,
        ).exists():
            raise serializers.ValidationError(
                "This expense category already exists in your hospital."
            )
        return value


class HospitalCategoryAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, AccountingRolePermission]

    model = None
    serializer_class = None
    response_key = None

    def get(self, request):
        categories = self.model.objects.filter(
            hospital_id=request.accounting_hospital_id
        ).order_by("name", "id")

        serializer = self.serializer_class(categories, many=True)

        return Response({
            "hospital_id": str(request.accounting_hospital_id),
            self.response_key: serializer.data,
        })

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                category = serializer.save(
                    hospital_id=request.accounting_hospital_id
                )
        except IntegrityError as exc:
            cause = getattr(exc, "__cause__", None)
            diag = getattr(cause, "diag", None)
            constraint = getattr(diag, "constraint_name", None)

            if constraint == "uq_exp_cat_hospital_name":
                raise serializers.ValidationError({
                    "name": "This expense category already exists."
                }) from exc
            raise

        return Response(
            {
                "hospital_id": str(request.accounting_hospital_id),
                "category": self.serializer_class(category).data,
            },
            status=status.HTTP_201_CREATED,
        )


class IncomeCategoryListAPIView(HospitalCategoryAPIView):
    model = IncomeCategory
    serializer_class = IncomeCategorySerializer
    response_key = "income_categories"


class ExpenseCategoryListAPIView(HospitalCategoryAPIView):
    model = ExpenseCategory
    serializer_class = ExpenseCategorySerializer
    response_key = "expense_categories"
