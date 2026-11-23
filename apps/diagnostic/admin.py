from django.contrib import admin

from .models import (
    TestCategory,
    DiagnosticTest,
    TestOrder,
    TestOrderItem,
    TestResult,
    DiagnosticReport,
)


@admin.register(TestCategory)
class TestCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "hospital_id", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


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
    list_filter = ("category", "sample_type", "is_active")
    search_fields = ("test_code", "name")


@admin.register(TestOrder)
class TestOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "hospital_id", "status", "created_at")
    list_filter = ("status", "created_at")


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
    )
    list_filter = ("status",)


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order_item",
        "parameter_name",
        "result_value",
        "unit",
        "flag",
    )
    search_fields = ("parameter_name",)


@admin.register(DiagnosticReport)
class DiagnosticReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order",
        "report_number",
        "status",
        "verified_at",
    )
    list_filter = ("status",)
    search_fields = ("report_number",)