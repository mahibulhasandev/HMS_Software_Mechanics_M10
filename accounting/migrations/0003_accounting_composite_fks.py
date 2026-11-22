
from django.db import migrations

# (child_table, reference_column, parent_table, constraint_name)
RELATIONSHIPS = [
    ("invoice_items", "invoice_id", "invoices",
     "fk_invitem_invoice_hospital"),

    ("payments", "invoice_id", "invoices",
     "fk_payment_invoice_hospital"),

    ("payments", "account_id", "accounts",
     "fk_payment_account_hospital"),

    ("payments", "refunded_payment_id", "payments",
     "fk_payment_refund_hospital"),

    ("expenses", "expense_category_id", "expense_categories",
     "fk_expense_category_hospital"),

    ("expenses", "account_id", "accounts",
     "fk_expense_account_hospital"),

    ("transactions", "account_id", "accounts",
     "fk_txn_account_hospital"),

    ("transactions", "income_category_id", "income_categories",
     "fk_txn_income_category_hospital"),

    ("transactions", "expense_category_id", "expense_categories",
     "fk_txn_expense_category_hospital"),

    ("transactions", "payment_id", "payments",
     "fk_txn_payment_hospital"),

    ("transactions", "expense_id", "expenses",
     "fk_txn_expense_hospital"),

    ("transactions", "reversed_transaction_id", "transactions",
     "fk_txn_reversal_hospital"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0002_invoiceitem_ck_inv_item_status_valid"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                f'ALTER TABLE "{child}" ADD CONSTRAINT "{name}" '
                f'FOREIGN KEY ("hospital_id", "{column}") '
                f'REFERENCES "{parent}" ("hospital_id", "id") '
                'ON DELETE RESTRICT;'
            ),
            reverse_sql=(
                f'ALTER TABLE "{child}" DROP CONSTRAINT "{name}";'
            ),
        )
        for child, column, parent, name in RELATIONSHIPS
    ]
