from rest_framework import serializers

from .models import (
    DiagnosticReport,
    DiagnosticTest,
    TestCategory,
    TestOrder,
    TestOrderItem,
    TestResult,
)


class TestCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TestCategory
        fields = [
            "id",
            "hospital_id",
            "name",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate_name(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Category name cannot be blank.")
        return cleaned


class DiagnosticTestSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    class Meta:
        model = DiagnosticTest
        fields = [
            "id",
            "hospital_id",
            "category",
            "category_name",
            "test_code",
            "name",
            "price",
            "sample_type",
            "turnaround_hours",
            "is_active",
        ]
        read_only_fields = ["id", "category_name"]

    def validate(self, attrs):
        hospital_id = attrs.get(
            "hospital_id",
            getattr(self.instance, "hospital_id", None),
        )
        category = attrs.get(
            "category",
            getattr(self.instance, "category", None),
        )

        if hospital_id and category and category.hospital_id != hospital_id:
            raise serializers.ValidationError(
                {"category": "Selected category does not belong to this hospital."}
            )

        if "price" in attrs and attrs["price"] is not None and attrs["price"] < 0:
            raise serializers.ValidationError(
                {"price": "Price cannot be negative."}
            )

        if (
            "turnaround_hours" in attrs
            and attrs["turnaround_hours"] is not None
            and attrs["turnaround_hours"] <= 0
        ):
            raise serializers.ValidationError(
                {"turnaround_hours": "Turnaround hours must be greater than zero."}
            )

        return attrs


class TestOrderItemSerializer(serializers.ModelSerializer):
    test_name = serializers.CharField(
        source="diagnostic_test.name",
        read_only=True,
    )
    test_code = serializers.CharField(
        source="diagnostic_test.test_code",
        read_only=True,
    )

    class Meta:
        model = TestOrderItem
        fields = [
            "id",
            "hospital_id",
            "test_order",
            "diagnostic_test",
            "test_name",
            "test_code",
            "processed_by_hospital_user_id",
            "price_at_order",
            "status",
            "sample_collected_at",
        ]
        read_only_fields = ["id", "test_name", "test_code"]

    def validate(self, attrs):
        hospital_id = attrs.get(
            "hospital_id",
            getattr(self.instance, "hospital_id", None),
        )
        test_order = attrs.get(
            "test_order",
            getattr(self.instance, "test_order", None),
        )
        diagnostic_test = attrs.get(
            "diagnostic_test",
            getattr(self.instance, "diagnostic_test", None),
        )

        if hospital_id and test_order and test_order.hospital_id != hospital_id:
            raise serializers.ValidationError(
                {"test_order": "Test order does not belong to this hospital."}
            )

        if hospital_id and diagnostic_test and diagnostic_test.hospital_id != hospital_id:
            raise serializers.ValidationError(
                {"diagnostic_test": "Diagnostic test does not belong to this hospital."}
            )

        if (
            "price_at_order" in attrs
            and attrs["price_at_order"] is not None
            and attrs["price_at_order"] < 0
        ):
            raise serializers.ValidationError(
                {"price_at_order": "Price at order cannot be negative."}
            )

        return attrs


class TestOrderSerializer(serializers.ModelSerializer):
    items = TestOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = TestOrder
        fields = [
            "id",
            "hospital_id",
            "status",
            "created_at",
            "items",
        ]
        read_only_fields = ["id", "created_at", "items"]


class TestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = [
            "id",
            "hospital_id",
            "test_order_item",
            "entered_by_hospital_user_id",
            "parameter_name",
            "result_value",
            "unit",
            "reference_range",
            "flag",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        hospital_id = attrs.get(
            "hospital_id",
            getattr(self.instance, "hospital_id", None),
        )
        test_order_item = attrs.get(
            "test_order_item",
            getattr(self.instance, "test_order_item", None),
        )

        if hospital_id and test_order_item and test_order_item.hospital_id != hospital_id:
            raise serializers.ValidationError(
                {"test_order_item": "Test order item does not belong to this hospital."}
            )

        return attrs


class DiagnosticReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticReport
        fields = [
            "id",
            "hospital_id",
            "test_order",
            "verified_by_hospital_user_id",
            "report_number",
            "summary",
            "status",
            "verified_at",
            "file_url",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        hospital_id = attrs.get(
            "hospital_id",
            getattr(self.instance, "hospital_id", None),
        )
        test_order = attrs.get(
            "test_order",
            getattr(self.instance, "test_order", None),
        )

        if hospital_id and test_order and test_order.hospital_id != hospital_id:
            raise serializers.ValidationError(
                {"test_order": "Test order does not belong to this hospital."}
            )

        return attrs