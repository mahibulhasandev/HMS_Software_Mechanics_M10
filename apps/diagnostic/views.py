from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    DiagnosticReport,
    DiagnosticTest,
    TestCategory,
    TestOrder,
    TestOrderItem,
)
from .serializers import (
    CreateTestOrderSerializer,
    DiagnosticReportSerializer,
    DiagnosticTestSerializer,
    TestCategorySerializer,
    TestOrderItemSerializer,
    TestOrderSerializer,
    TestResultSerializer,
)
from .services import (
    add_test_result,
    create_test_order,
    get_accessible_report,
    mark_sample_collected,
    verify_diagnostic_report,
)


class TestCategoryViewSet(viewsets.ModelViewSet):
    queryset = TestCategory.objects.all()
    serializer_class = TestCategorySerializer


class DiagnosticTestViewSet(viewsets.ModelViewSet):
    queryset = DiagnosticTest.objects.select_related("category").all()
    serializer_class = DiagnosticTestSerializer


class TestOrderViewSet(viewsets.ModelViewSet):
    queryset = TestOrder.objects.prefetch_related("items__results").all()
    serializer_class = TestOrderSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = CreateTestOrderSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            order = create_test_order(**input_serializer.validated_data)
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            TestOrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class TestOrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        TestOrderItem.objects.select_related("test_order", "diagnostic_test")
        .prefetch_related("results")
        .all()
    )
    serializer_class = TestOrderItemSerializer

    @action(detail=True, methods=["post"], url_path="collect-sample")
    def collect_sample(self, request, pk=None):
        hospital_id = request.data.get("hospital_id")
        if not hospital_id:
            return Response(
                {"detail": "hospital_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = mark_sample_collected(
                order_item_id=pk,
                hospital_id=hospital_id,
                processed_by_hospital_user_id=request.data.get(
                    "processed_by_hospital_user_id"
                ),
            )
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TestOrderItemSerializer(item).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="add-result")
    def add_result(self, request, pk=None):
        required_fields = [
            "hospital_id",
            "entered_by_hospital_user_id",
            "parameter_name",
            "result_value",
        ]
        missing = [field for field in required_fields if not request.data.get(field)]
        if missing:
            return Response(
                {"detail": f"Missing required fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = add_test_result(
                order_item_id=pk,
                hospital_id=request.data["hospital_id"],
                entered_by_hospital_user_id=request.data[
                    "entered_by_hospital_user_id"
                ],
                parameter_name=request.data["parameter_name"],
                result_value=request.data["result_value"],
                unit=request.data.get("unit", ""),
                reference_range=request.data.get("reference_range", ""),
                flag=request.data.get("flag", ""),
                mark_item_completed=bool(
                    request.data.get("mark_item_completed", False)
                ),
            )
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TestResultSerializer(result).data, status=status.HTTP_201_CREATED)


class DiagnosticReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DiagnosticReport.objects.select_related("test_order").all()
    serializer_class = DiagnosticReportSerializer

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        hospital_id = request.data.get("hospital_id")
        verified_by = request.data.get("verified_by_hospital_user_id")
        if not hospital_id or not verified_by:
            return Response(
                {
                    "detail": "hospital_id and verified_by_hospital_user_id are required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = verify_diagnostic_report(
                report_id=pk,
                hospital_id=hospital_id,
                verified_by_hospital_user_id=verified_by,
                summary=request.data.get("summary"),
                file_url=request.data.get("file_url"),
            )
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(DiagnosticReportSerializer(report).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="final-report")
    def final_report(self, request, pk=None):
        hospital_id = request.query_params.get("hospital_id")
        if not hospital_id:
            return Response(
                {"detail": "hospital_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = get_accessible_report(report_id=pk, hospital_id=hospital_id)
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(DiagnosticReportSerializer(report).data, status=status.HTTP_200_OK)