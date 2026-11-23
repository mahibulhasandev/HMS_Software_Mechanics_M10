
import uuid

from django.db import models
from django.core.exceptions import ValidationError


class MedicineCategory(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="medicine_categories",
    )

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pharmacy_medicine_categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "name"],
                name="pharmacy_unique_category",
            )
        ]

    def __str__(self):
        return self.name


class Manufacturer(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="medicine_manufacturers",
    )

    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100, blank=True)
    contact_number = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_manufacturers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "name"],
                name="pharmacy_unique_manufacturer",
            )
        ]

    def __str__(self):
        return self.name


class Supplier(models.Model):
    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="pharmacy_suppliers",
    )

    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pharmacy_suppliers"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "name"],
                name="pharmacy_unique_supplier",
            )
        ]

    def __str__(self):
        return self.name


class Medicine(models.Model):

    class MedicineType(models.TextChoices):
        TABLET = "tablet", "Tablet"
        CAPSULE = "capsule", "Capsule"
        SYRUP = "syrup", "Syrup"
        INJECTION = "injection", "Injection"
        CREAM = "cream", "Cream"
        OINTMENT = "ointment", "Ointment"
        DROPS = "drops", "Drops"
        INHALER = "inhaler", "Inhaler"
        OTHER = "other", "Other"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="medicines",
    )

    category = models.ForeignKey(
        MedicineCategory,
        on_delete=models.PROTECT,
        related_name="medicines",
    )

    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="medicines",
        null=True,
        blank=True,
    )

    medicine_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    medicine_type = models.CharField(
        max_length=20,
        choices=MedicineType.choices,
        default=MedicineType.TABLET,
    )

    strength = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=50, default="Piece")

    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    reorder_level = models.PositiveIntegerField(default=10)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pharmacy_medicines"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "medicine_code"],
                name="pharmacy_unique_medicine_code",
            ),
            models.CheckConstraint(
                condition=models.Q(purchase_price__gte=0),
                name="pharmacy_medicine_purchase_price",
            ),
            models.CheckConstraint(
                condition=models.Q(selling_price__gte=0),
                name="pharmacy_medicine_selling_price",
            ),
        ]
        indexes = [
            models.Index(fields=["hospital", "name"]),
            models.Index(fields=["hospital", "is_active"]),
        ]

    def clean(self):
        if self.category_id and self.hospital_id:
            if self.category.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Medicine category and hospital must match."
                )

        if self.manufacturer_id and self.hospital_id:
            if self.manufacturer.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Manufacturer and hospital must match."
                )

    def __str__(self):
        return f"{self.name} ({self.strength})"


class MedicineBatch(models.Model):

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="medicine_batches",
    )

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name="batches",
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="medicine_batches",
        null=True,
        blank=True,
    )

    batch_number = models.CharField(max_length=100)
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField()

    quantity_received = models.PositiveIntegerField()
    quantity_available = models.PositiveIntegerField()

    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    selling_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_medicine_batches"
        ordering = ["expiry_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "medicine", "batch_number"],
                name="pharmacy_unique_batch",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_available__lte=models.F(
                    "quantity_received"
                )),
                name="pharmacy_batch_stock_limit",
            ),
            models.CheckConstraint(
                condition=models.Q(purchase_price__gte=0),
                name="pharmacy_batch_purchase_price",
            ),
            models.CheckConstraint(
                condition=models.Q(selling_price__gte=0),
                name="pharmacy_batch_selling_price",
            ),
        ]
        indexes = [
            models.Index(fields=["hospital", "expiry_date"]),
            models.Index(fields=["medicine", "expiry_date"]),
        ]

    def clean(self):
        if self.medicine_id and self.hospital_id:
            if self.medicine.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Medicine and batch hospital must match."
                )

        if self.supplier_id and self.hospital_id:
            if self.supplier.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Supplier and batch hospital must match."
                )

        if (
            self.manufacturing_date
            and self.manufacturing_date > self.expiry_date
        ):
            raise ValidationError(
                "Manufacturing date cannot be after expiry date."
            )

    def __str__(self):
        return f"{self.medicine.name} - {self.batch_number}"


class Purchase(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="pharmacy_purchases",
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchases",
    )

    purchase_number = models.CharField(max_length=50)
    purchase_date = models.DateField()
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_purchases"
        ordering = ["-purchase_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "purchase_number"],
                name="pharmacy_unique_purchase_number",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name="pharmacy_purchase_subtotal",
            ),
            models.CheckConstraint(
                condition=models.Q(discount__gte=0),
                name="pharmacy_purchase_discount",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="pharmacy_purchase_total",
            ),
        ]

    def clean(self):
        if self.supplier_id and self.hospital_id:
            if self.supplier.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Supplier and purchase hospital must match."
                )

    def __str__(self):
        return self.purchase_number


class PurchaseItem(models.Model):

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="pharmacy_purchase_items",
    )

    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="items",
    )

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name="purchase_items",
    )

    batch_number = models.CharField(max_length=100)
    manufacturing_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField()

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    class Meta:
        db_table = "pharmacy_purchase_items"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="pharmacy_purchase_item_qty",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="pharmacy_purchase_item_price",
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0),
                name="pharmacy_purchase_item_total",
            ),
        ]

    def clean(self):
        if self.purchase_id and self.hospital_id:
            if self.purchase.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Purchase and item hospital must match."
                )

        if self.medicine_id and self.hospital_id:
            if self.medicine.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Medicine and item hospital must match."
                )


class MedicineSale(models.Model):

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="medicine_sales",
    )

    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.PROTECT,
        related_name="medicine_sales",
        null=True,
        blank=True,
    )

    prescription = models.ForeignKey(
        "clinic.Prescription",
        on_delete=models.PROTECT,
        related_name="medicine_sales",
        null=True,
        blank=True,
    )

    invoice_id = models.UUIDField(null=True, blank=True)

    sale_number = models.CharField(max_length=50)
    sale_date = models.DateTimeField()

    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_medicine_sales"
        ordering = ["-sale_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["hospital", "sale_number"],
                name="pharmacy_unique_sale_number",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name="pharmacy_sale_subtotal",
            ),
            models.CheckConstraint(
                condition=models.Q(discount__gte=0),
                name="pharmacy_sale_discount",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=0),
                name="pharmacy_sale_total",
            ),
        ]

    def clean(self):
        if self.patient_id and self.hospital_id:
            if self.patient.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Patient and sale hospital must match."
                )

        if self.prescription_id and self.hospital_id:
            if self.prescription.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Prescription and sale hospital must match."
                )

    def __str__(self):
        return self.sale_number


class MedicineSaleItem(models.Model):

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="pharmacy_sale_items",
    )

    sale = models.ForeignKey(
        MedicineSale,
        on_delete=models.CASCADE,
        related_name="items",
    )

    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name="sale_items",
    )

    prescription_item = models.ForeignKey(
        "clinic.PrescriptionItem",
        on_delete=models.PROTECT,
        related_name="sale_items",
        null=True,
        blank=True,
    )

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    discount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    total_price = models.DecimalField(
        max_digits=12, decimal_places=2
    )

    class Meta:
        db_table = "pharmacy_medicine_sale_items"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="pharmacy_sale_item_qty",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="pharmacy_sale_item_price",
            ),
            models.CheckConstraint(
                condition=models.Q(discount__gte=0),
                name="pharmacy_sale_item_discount",
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gte=0),
                name="pharmacy_sale_item_total",
            ),
        ]

    def clean(self):
        if self.sale_id and self.hospital_id:
            if self.sale.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Sale and item hospital must match."
                )

        if self.batch_id and self.hospital_id:
            if self.batch.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Batch and item hospital must match."
                )

    def __str__(self):
        return f"{self.batch.medicine.name} x {self.quantity}"


class StockTransaction(models.Model):

    class TransactionType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        RETURN = "return", "Return"
        ADJUSTMENT = "adjustment", "Adjustment"
        EXPIRED = "expired", "Expired"
        DAMAGE = "damage", "Damaged"

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.PROTECT,
        related_name="pharmacy_stock_transactions",
    )

    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name="stock_transactions",
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
    )

    # Positive = stock in; negative = stock out.
    quantity_change = models.IntegerField()

    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "pharmacy_stock_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["hospital", "created_at"]),
            models.Index(fields=["batch", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity_change=0),
                name="pharmacy_stock_nonzero_change",
            )
        ]

    def clean(self):
        if self.batch_id and self.hospital_id:
            if self.batch.hospital_id != self.hospital_id:
                raise ValidationError(
                    "Batch and stock transaction hospital must match."
                )

    def __str__(self):
        return f"{self.transaction_type} - {self.quantity_change}"
