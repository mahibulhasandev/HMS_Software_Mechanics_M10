
from django.contrib import admin

from .models import (
    MedicineCategory,
    Manufacturer,
    Supplier,
    Medicine,
    MedicineBatch,
    Purchase,
    PurchaseItem,
    MedicineSale,
    MedicineSaleItem,
    StockTransaction,
)


@admin.register(MedicineCategory)
class MedicineCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "hospital", "is_active")
    list_filter = ("is_active", "hospital")
    search_fields = ("name",)


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "hospital", "is_active")
    list_filter = ("is_active", "country")
    search_fields = ("name",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_person", "phone", "hospital", "is_active")
    list_filter = ("is_active", "hospital")
    search_fields = ("name", "phone", "email")


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = (
        "medicine_code",
        "name",
        "generic_name",
        "category",
        "selling_price",
        "is_active",
    )
    list_filter = ("category", "medicine_type", "is_active", "hospital")
    search_fields = ("medicine_code", "name", "generic_name")


@admin.register(MedicineBatch)
class MedicineBatchAdmin(admin.ModelAdmin):
    list_display = (
        "medicine",
        "batch_number",
        "expiry_date",
        "quantity_available",
        "selling_price",
    )
    list_filter = ("expiry_date", "hospital")
    search_fields = ("medicine__name", "batch_number")


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "purchase_number",
        "supplier",
        "purchase_date",
        "total_amount",
        "status",
    )
    list_filter = ("status", "purchase_date", "hospital")
    search_fields = ("purchase_number", "supplier__name")
    inlines = [PurchaseItemInline]


class MedicineSaleItemInline(admin.TabularInline):
    model = MedicineSaleItem
    extra = 1


@admin.register(MedicineSale)
class MedicineSaleAdmin(admin.ModelAdmin):
    list_display = (
        "sale_number",
        "patient",
        "sale_date",
        "total_amount",
        "status",
    )
    list_filter = ("status", "sale_date", "hospital")
    search_fields = ("sale_number", "patient__first_name")
    inlines = [MedicineSaleItemInline]


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "batch",
        "transaction_type",
        "quantity_change",
        "reference_number",
        "created_at",
    )
    list_filter = ("transaction_type", "created_at", "hospital")
    search_fields = ("reference_number", "batch__batch_number")
