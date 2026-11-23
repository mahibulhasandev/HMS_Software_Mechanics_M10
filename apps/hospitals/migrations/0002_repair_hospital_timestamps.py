from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("hospitals", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'hospitals'
                                  AND column_name = 'created_at'
                            ) THEN
                                ALTER TABLE hospitals
                                ADD COLUMN created_at timestamptz;
                            END IF;

                            IF NOT EXISTS (
                                SELECT 1
                                FROM information_schema.columns
                                WHERE table_schema = current_schema()
                                  AND table_name = 'hospitals'
                                  AND column_name = 'updated_at'
                            ) THEN
                                ALTER TABLE hospitals
                                ADD COLUMN updated_at timestamptz;
                            END IF;
                        END $$;

                        UPDATE hospitals
                        SET
                            created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
                            updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP);

                        ALTER TABLE hospitals
                        ALTER COLUMN created_at SET NOT NULL,
                        ALTER COLUMN updated_at SET NOT NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],
        ),
    ]