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
        fields = "__all__"


class DiagnosticTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticTest
        fields = "__all__"


class TestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = "__all__"


class TestOrderItemSerializer(serializers.ModelSerializer):
    results = TestResultSerializer(many=True, read_only=True)

    class Meta:
        model = TestOrderItem
        fields = "__all__"


class TestOrderSerializer(serializers.ModelSerializer):
    items = TestOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = TestOrder
        fields = "__all__"


class CreateTestOrderSerializer(serializers.Serializer):
    hospital_id = serializers.UUIDField()
    patient_id = serializers.UUIDField()
    test_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )
    priority = serializers.CharField(required=False, default="routine")
    patient_visit_id = serializers.UUIDField(required=False, allow_null=True)
    ordered_by_doctor_id = serializers.UUIDField(required=False, allow_null=True)


class DiagnosticReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticReport
        fields = "__all__"