
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        (
            "accounting",
            "0003_accounting_composite_fks"
        ),
    ]

    operations = [

        # 1. Create a function that rejects changes
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION accounting_block_ledger_change()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        'Transactions are append-only. Operation % is prohibited.',
                        TG_OP;

                    RETURN NULL;
                END;
                $$;
            """,
            reverse_sql="""
                DROP FUNCTION accounting_block_ledger_change();
            """,
        ),

        # 2. Block UPDATE and DELETE
        migrations.RunSQL(
            sql="""
                CREATE TRIGGER trg_transactions_no_update_delete
                BEFORE UPDATE OR DELETE
                ON transactions
                FOR EACH ROW
                EXECUTE FUNCTION accounting_block_ledger_change();
            """,
            reverse_sql="""
                DROP TRIGGER trg_transactions_no_update_delete
                ON transactions;
            """,
        ),

        # 3. Block TRUNCATE
        migrations.RunSQL(
            sql="""
                CREATE TRIGGER trg_transactions_no_truncate
                BEFORE TRUNCATE
                ON transactions
                FOR EACH STATEMENT
                EXECUTE FUNCTION accounting_block_ledger_change();
            """,
            reverse_sql="""
                DROP TRIGGER trg_transactions_no_truncate
                ON transactions;
            """,
        ),
    ]
