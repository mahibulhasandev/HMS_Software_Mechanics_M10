from django.contrib import admin

from .models import (
    DiagnosticReport,
    DiagnosticTest,
    TestCategory,
    TestOrder,
    TestOrderItem,
    TestResult,
)


@admin.register(TestCategory)
class TestCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "name",
        "is_active",
    )
    list_filter = (
        "is_active",
        "hospital_id",
    )
    search_fields = (
        "name",
    )


@admin.register(DiagnosticTest)
class DiagnosticTestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "category",
        "test_code",
        "name",
        "price",
        "sample_type",
        "turnaround_hours",
        "is_active",
    )
    list_filter = (
        "is_active",
        "category",
        "sample_type",
        "hospital_id",
    )
    search_fields = (
        "test_code",
        "name",
        "sample_type",
    )


@admin.register(TestOrder)
class TestOrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "hospital_id",
    )
    search_fields = (
        "status",
    )


@admin.register(TestOrderItem)
class TestOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order",
        "diagnostic_test",
        "price_at_order",
        "status",
        "sample_collected_at",
        "processed_by_hospital_user_id",
    )
    list_filter = (
        "status",
        "hospital_id",
    )
    search_fields = (
        "diagnostic_test__test_code",
        "diagnostic_test__name",
    )


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order_item",
        "entered_by_hospital_user_id",
        "parameter_name",
        "result_value",
        "unit",
        "reference_range",
        "flag",
    )
    list_filter = (
        "flag",
        "hospital_id",
    )
    search_fields = (
        "parameter_name",
        "result_value",
        "flag",
    )


@admin.register(DiagnosticReport)
class DiagnosticReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order",
        "verified_by_hospital_user_id",
        "report_number",
        "status",
        "verified_at",
        "file_url",
    )
    list_filter = (
        "status",
        "hospital_id",
    )
    search_fields = (
        "report_number",
        "summary",
    )