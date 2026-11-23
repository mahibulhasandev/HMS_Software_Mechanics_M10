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
        "test_code",
        "name",
        "category",
        "price",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("test_code", "name")


@admin.register(TestOrder)
class TestOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "hospital_id", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("id",)


@admin.register(TestOrderItem)
class TestOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order",
        "diagnostic_test",
        "status",
        "sample_collected_at",
    )
    list_filter = ("status",)
    search_fields = ("id",)


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hospital_id",
        "test_order_item",
        "parameter_name",
        "result_value",
        "flag",
    )
    search_fields = ("parameter_name", "result_value")


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