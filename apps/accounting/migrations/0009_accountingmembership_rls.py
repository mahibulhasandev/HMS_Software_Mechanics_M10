from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0008_accountingmembership"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                GRANT SELECT
                ON TABLE accounting_memberships
                TO hms_app;

                ALTER TABLE accounting_memberships
                ENABLE ROW LEVEL SECURITY;

                ALTER TABLE accounting_memberships
                FORCE ROW LEVEL SECURITY;

                CREATE POLICY accounting_membership_self_read
                ON accounting_memberships
                FOR SELECT
                TO hms_app
                USING (
                    user_id = NULLIF(
                        current_setting('app.user_id', true),
                        ''
                    )::integer
                );
            """,
            reverse_sql="""
                DROP POLICY IF EXISTS
                accounting_membership_self_read
                ON accounting_memberships;

                ALTER TABLE accounting_memberships
                NO FORCE ROW LEVEL SECURITY;

                ALTER TABLE accounting_memberships
                DISABLE ROW LEVEL SECURITY;

                REVOKE SELECT
                ON TABLE accounting_memberships
                FROM hms_app;
            """,
        ),
    ]
