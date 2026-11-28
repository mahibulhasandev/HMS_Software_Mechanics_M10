from django.db import migrations


FORWARD_SQL = '''

LOCK TABLE
    public.payments,
    public.expenses,
    public.transactions
IN SHARE ROW EXCLUSIVE MODE;

SET LOCAL row_security = off;


-- Validate historical payment and refund ledger records.

DO $$
BEGIN

    IF EXISTS (

        SELECT 1

        FROM public.transactions t

        LEFT JOIN public.payments p
            ON p.id = t.payment_id

        WHERE t.payment_id IS NOT NULL

        AND (
            p.id IS NULL

            OR p.hospital_id
                IS DISTINCT FROM t.hospital_id

            OR p.account_id
                IS DISTINCT FROM t.account_id

            OR p.amount
                IS DISTINCT FROM t.amount

            OR p.status <> 'completed'

            OR NOT (
                (
                    p.kind = 'payment'
                    AND t.transaction_type = 'income'
                )
                OR
                (
                    p.kind = 'refund'
                    AND t.transaction_type = 'refund'
                )
            )
        )

    ) THEN

        RAISE EXCEPTION
            'Existing payment ledger inconsistency detected.';

    END IF;


    -- Previously reversed expenses retain their
    -- original expense ledger entries.

    IF EXISTS (

        SELECT 1

        FROM public.transactions t

        LEFT JOIN public.expenses e
            ON e.id = t.expense_id

        WHERE t.expense_id IS NOT NULL

        AND (
            e.id IS NULL

            OR e.hospital_id
                IS DISTINCT FROM t.hospital_id

            OR e.account_id
                IS DISTINCT FROM t.account_id

            OR e.amount
                IS DISTINCT FROM t.amount

            OR e.expense_category_id
                IS DISTINCT FROM t.expense_category_id

            OR e.status NOT IN ('paid', 'reversed')

            OR t.transaction_type <> 'expense'
        )

    ) THEN

        RAISE EXCEPTION
            'Existing expense ledger inconsistency detected.';

    END IF;

END;
$$;


CREATE FUNCTION public.accounting_validate_ledger_source()

RETURNS trigger

LANGUAGE plpgsql

SECURITY INVOKER

SET search_path = pg_catalog, public

AS $$

DECLARE

    source_payment public.payments%ROWTYPE;

    source_expense public.expenses%ROWTYPE;

BEGIN

    -- Reversals are protected by migration 0012.

    IF NEW.transaction_type = 'reversal' THEN

        RETURN NEW;

    END IF;


    -- Validate payment and refund transactions.

    IF NEW.transaction_type IN ('income', 'refund') THEN

        SELECT *
        INTO source_payment

        FROM public.payments

        WHERE id = NEW.payment_id

        AND hospital_id = NEW.hospital_id;

        IF NOT FOUND THEN

            RAISE EXCEPTION USING

                ERRCODE = '23514',

                CONSTRAINT = 'ck_txn_payment_source_integrity',

                MESSAGE = 'Ledger requires a valid payment source.';

        END IF;


        IF source_payment.status <> 'completed'

        OR source_payment.account_id
            IS DISTINCT FROM NEW.account_id

        OR source_payment.amount
            IS DISTINCT FROM NEW.amount

        OR NOT (
            (
                source_payment.kind = 'payment'
                AND NEW.transaction_type = 'income'
            )
            OR
            (
                source_payment.kind = 'refund'
                AND NEW.transaction_type = 'refund'
            )
        )

        THEN

            RAISE EXCEPTION USING

                ERRCODE = '23514',

                CONSTRAINT = 'ck_txn_payment_source_integrity',

                MESSAGE = 'Ledger does not match completed payment or refund.';

        END IF;


    -- Validate expense transactions.

    ELSIF NEW.transaction_type = 'expense' THEN

        SELECT *
        INTO source_expense

        FROM public.expenses

        WHERE id = NEW.expense_id

        AND hospital_id = NEW.hospital_id;

        IF NOT FOUND THEN

            RAISE EXCEPTION USING

                ERRCODE = '23514',

                CONSTRAINT = 'ck_txn_expense_source_integrity',

                MESSAGE = 'Ledger requires a valid expense source.';

        END IF;


        IF source_expense.status <> 'paid'

        OR source_expense.account_id
            IS DISTINCT FROM NEW.account_id

        OR source_expense.amount
            IS DISTINCT FROM NEW.amount

        OR source_expense.expense_category_id
            IS DISTINCT FROM NEW.expense_category_id

        THEN

            RAISE EXCEPTION USING

                ERRCODE = '23514',

                CONSTRAINT = 'ck_txn_expense_source_integrity',

                MESSAGE = 'Ledger does not match paid expense.';

        END IF;

    END IF;

    RETURN NEW;

END;

$$;


CREATE TRIGGER trg_transactions_validate_source

BEFORE INSERT

ON public.transactions

FOR EACH ROW

EXECUTE FUNCTION public.accounting_validate_ledger_source();

'''


REVERSE_SQL = '''

DROP TRIGGER IF EXISTS
    trg_transactions_validate_source
ON public.transactions;

DROP FUNCTION IF EXISTS
    public.accounting_validate_ledger_source();

'''


class Migration(migrations.Migration):

    atomic = True

    dependencies = [
        ("accounting", "0013_invoice_financial_consistency"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
