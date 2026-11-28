from django.db import migrations


FORWARD_SQL = '''

-- Prevent concurrent ledger writes during migration validation.

LOCK TABLE public.transactions
IN SHARE ROW EXCLUSIVE MODE;

-- Fail safely if the migration role cannot inspect all rows.

SET LOCAL row_security = off;

-- Reject migration if inconsistent historical reversals exist.

DO $$
BEGIN

    IF EXISTS (

        SELECT 1

        FROM public.transactions r

        LEFT JOIN public.transactions original
            ON original.id = r.reversed_transaction_id

        WHERE r.transaction_type = 'reversal'

        AND (
            original.id IS NULL

            OR original.hospital_id
                IS DISTINCT FROM r.hospital_id

            OR original.account_id
                IS DISTINCT FROM r.account_id

            OR original.amount
                IS DISTINCT FROM r.amount

            OR original.transaction_type NOT IN (
                'income', 'expense', 'refund'
            )
        )
    ) THEN

        RAISE EXCEPTION
            'Existing invalid reversals must be resolved before migration.';

    END IF;

END;
$$;


-- Validate every new reversal at database level.

CREATE FUNCTION public.accounting_validate_reversal()
RETURNS trigger

LANGUAGE plpgsql

SECURITY INVOKER

SET search_path = pg_catalog, public

AS $$

DECLARE

    original public.transactions%ROWTYPE;

BEGIN

    IF NEW.transaction_type <> 'reversal' THEN

        RETURN NEW;

    END IF;

    SELECT *
    INTO original

    FROM public.transactions

    WHERE id = NEW.reversed_transaction_id

    AND hospital_id = NEW.hospital_id;

    IF NOT FOUND THEN

        RAISE EXCEPTION USING

            ERRCODE = '23514',

            CONSTRAINT = 'ck_txn_reversal_matches_original',

            MESSAGE = 'Reversal requires a valid original transaction.';

    END IF;

    IF original.transaction_type NOT IN (
        'income', 'expense', 'refund'
    )

    OR original.account_id
        IS DISTINCT FROM NEW.account_id

    OR original.amount
        IS DISTINCT FROM NEW.amount

    THEN

        RAISE EXCEPTION USING

            ERRCODE = '23514',

            CONSTRAINT = 'ck_txn_reversal_matches_original',

            MESSAGE = 'Reversal does not match original transaction.';

    END IF;

    RETURN NEW;

END;

$$;


CREATE TRIGGER trg_transactions_validate_reversal

BEFORE INSERT

ON public.transactions

FOR EACH ROW

EXECUTE FUNCTION public.accounting_validate_reversal();


-- Prevent modification of expense idempotency identity.

CREATE FUNCTION public.accounting_preserve_expense_idempotency()

RETURNS trigger

LANGUAGE plpgsql

SECURITY INVOKER

SET search_path = pg_catalog, public

AS $$

BEGIN

    IF NEW.idempotency_key
        IS DISTINCT FROM OLD.idempotency_key

    OR NEW.request_fingerprint
        IS DISTINCT FROM OLD.request_fingerprint

    OR (
        OLD.idempotency_key IS NOT NULL

        AND (
            NEW.hospital_id
                IS DISTINCT FROM OLD.hospital_id

            OR NEW.id
                IS DISTINCT FROM OLD.id
        )
    )

    THEN

        RAISE EXCEPTION USING

            ERRCODE = '23514',

            CONSTRAINT = 'ck_expense_idempotency_immutable',

            MESSAGE = 'Expense idempotency identity is immutable.';

    END IF;

    RETURN NEW;

END;

$$;


CREATE TRIGGER trg_expenses_preserve_idempotency

BEFORE UPDATE

ON public.expenses

FOR EACH ROW

EXECUTE FUNCTION public.accounting_preserve_expense_idempotency();

'''


REVERSE_SQL = '''

DROP TRIGGER IF EXISTS
    trg_expenses_preserve_idempotency
ON public.expenses;

DROP FUNCTION IF EXISTS
    public.accounting_preserve_expense_idempotency();

DROP TRIGGER IF EXISTS
    trg_transactions_validate_reversal
ON public.transactions;

DROP FUNCTION IF EXISTS
    public.accounting_validate_reversal();

'''


class Migration(migrations.Migration):

    atomic = True

    dependencies = [
        ("accounting", "0011_expense_idempotency"),
    ]

    operations = [

        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),

    ]
