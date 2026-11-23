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
                        ALTER TABLE hospitals
                        ADD COLUMN created_at timestamptz,
                        ADD COLUMN updated_at timestamptz;

                        UPDATE hospitals
                        SET
                            created_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP;

                        ALTER TABLE hospitals
                        ALTER COLUMN created_at SET NOT NULL,
                        ALTER COLUMN updated_at SET NOT NULL;
                    """,
                    reverse_sql="""
                        ALTER TABLE hospitals
                        DROP COLUMN updated_at,
                        DROP COLUMN created_at;
                    """,
                ),
            ],
            state_operations=[],
        ),
    ]
