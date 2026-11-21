
from django.db import migrations


ACCOUNTING_TABLES = (
    "accounts",
    "income_categories",
    "expense_categories",
    "invoices",
    "invoice_items",
    "payments",
    "expenses",
    "transactions",
)

POLICY_NAME = "accounting_hospital_isolation"

HOSPITAL_CONDITION = (
    '"hospital_id" = '
    "NULLIF(current_setting('app.hospital_id', true), '')::uuid"
)


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0004_transaction_append_only"),
    ]

    operations = [
        operation
        for table in ACCOUNTING_TABLES
        for operation in (

            # Enable RLS
            migrations.RunSQL(
                sql=(
                    f'ALTER TABLE "{table}" '
                    'ENABLE ROW LEVEL SECURITY;'
                ),
                reverse_sql=(
                    f'ALTER TABLE "{table}" '
                    'DISABLE ROW LEVEL SECURITY;'
                ),
            ),

            # Apply RLS to table owners as well
            migrations.RunSQL(
                sql=(
                    f'ALTER TABLE "{table}" '
                    'FORCE ROW LEVEL SECURITY;'
                ),
                reverse_sql=(
                    f'ALTER TABLE "{table}" '
                    'NO FORCE ROW LEVEL SECURITY;'
                ),
            ),

            # Hospital-scoped policy for restricted role
            migrations.RunSQL(
                sql=(
                    f'CREATE POLICY "{POLICY_NAME}" '
                    f'ON "{table}" '
                    'FOR ALL TO hms_app '
                    f'USING ({HOSPITAL_CONDITION}) '
                    f'WITH CHECK ({HOSPITAL_CONDITION});'
                ),
                reverse_sql=(
                    f'DROP POLICY "{POLICY_NAME}" '
                    f'ON "{table}";'
                ),
            ),
        )
    ]
