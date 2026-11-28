from django.db import migrations


FORWARD_SQL = """
GRANT SELECT
ON TABLE public.accounting_memberships
TO hms_app;

ALTER TABLE public.accounting_memberships
ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.accounting_memberships
FORCE ROW LEVEL SECURITY;

DO $$
DECLARE
    user_id_type text;
BEGIN

    SELECT format_type(a.atttypid, a.atttypmod)
    INTO user_id_type
    FROM pg_attribute a
    WHERE a.attrelid =
        'public.accounting_memberships'::regclass
    AND a.attname = 'user_id'
    AND a.attnum > 0
    AND NOT a.attisdropped;

    IF user_id_type IS NULL THEN
        RAISE EXCEPTION
            'Cannot determine accounting_memberships.user_id type.';
    END IF;

    IF user_id_type NOT IN (
        'smallint',
        'integer',
        'bigint',
        'uuid'
    ) THEN
        RAISE EXCEPTION
            'Unsupported accounting user ID type: %',
            user_id_type;
    END IF;

    EXECUTE format(
        'CREATE POLICY accounting_membership_self_read
         ON public.accounting_memberships
         FOR SELECT
         TO hms_app
         USING (
             user_id = NULLIF(
                 current_setting(''app.user_id'', true),
                 ''''
             )::%s
         )',
        user_id_type
    );

END $$;
"""


REVERSE_SQL = """
DROP POLICY IF EXISTS
accounting_membership_self_read
ON public.accounting_memberships;

ALTER TABLE public.accounting_memberships
NO FORCE ROW LEVEL SECURITY;

ALTER TABLE public.accounting_memberships
DISABLE ROW LEVEL SECURITY;

REVOKE SELECT
ON TABLE public.accounting_memberships
FROM hms_app;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0008_accountingmembership"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
