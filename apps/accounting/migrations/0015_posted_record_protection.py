from django.db import migrations


FORWARD_SQL = '''

LOCK TABLE
    public.payments,
    public.expenses,
    public.transactions
IN SHARE ROW EXCLUSIVE MODE;


CREATE FUNCTION public.accounting_protect_completed_payment()

RETURNS trigger

LANGUAGE plpgsql

SECURITY INVOKER

SET search_path = pg_catalog, public

AS $$

BEGIN

    IF OLD.status = 'completed' THEN

        IF TG_OP = 'DELETE' THEN

            RAISE EXCEPTION USING
                ERRCODE = '23514',
                CONSTRAINT = 'ck_payment_completed_immutable',
                MESSAGE = 'Completed payments and refunds cannot be deleted.';

        ELSIF NEW IS DISTINCT FROM OLD THEN

            RAISE EXCEPTION USING
                ERRCODE = '23514',
                CONSTRAINT = 'ck_payment_completed_immutable',
                MESSAGE = 'Completed payments and refunds cannot be modified.';

        END IF;

    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;

END;

$$;


CREATE TRIGGER trg_payments_protect_completed

BEFORE UPDATE OR DELETE

ON public.payments

FOR EACH ROW

EXECUTE FUNCTION public.accounting_protect_completed_payment();



CREATE FUNCTION public.accounting_protect_posted_expense()

RETURNS trigger

LANGUAGE plpgsql

SECURITY INVOKER

SET search_path = pg_catalog, public

AS $$

BEGIN

    -- Protect posted expense records from deletion.

    IF TG_OP = 'DELETE' THEN

        IF OLD.status IN ('paid', 'reversed') THEN

            RAISE EXCEPTION USING
                ERRCODE = '23514',
                CONSTRAINT = 'ck_expense_posted_immutable',
                MESSAGE = 'Posted expenses cannot be deleted.';

        END IF;

        RETURN OLD;

    END IF;


    -- Allow unchanged rows.

    IF NEW IS NOT DISTINCT FROM OLD THEN

        RETURN NEW;

    END IF;


    -- Unposted expenses cannot move directly
    -- to reversed through an update.

    IF OLD.status NOT IN ('paid', 'reversed') THEN

        IF NEW.status = 'reversed' THEN

            RAISE EXCEPTION USING
                ERRCODE = '23514',
                CONSTRAINT = 'ck_expense_reversal_required',
                MESSAGE = 'Only paid expenses can be reversed.';

        END IF;

        RETURN NEW;

    END IF;


    -- The only permitted posted expense change
    -- is paid -> reversed.

    IF OLD.status = 'paid'
       AND NEW.status = 'reversed'

       AND (
           to_jsonb(NEW) - 'status'
       ) = (
           to_jsonb(OLD) - 'status'
       )

    THEN

        -- Require a matching original expense
        -- ledger and its reversal entry.

        IF NOT EXISTS (

            SELECT 1

            FROM public.transactions original

            JOIN public.transactions reversal

                ON reversal.reversed_transaction_id
                    = original.id

            WHERE original.expense_id = OLD.id

            AND original.hospital_id = OLD.hospital_id

            AND original.transaction_type = 'expense'

            AND original.account_id = OLD.account_id

            AND original.amount = OLD.amount

            AND original.expense_category_id
                = OLD.expense_category_id

            AND reversal.hospital_id = OLD.hospital_id

            AND reversal.transaction_type = 'reversal'

            AND reversal.account_id = OLD.account_id

            AND reversal.amount = OLD.amount

            AND reversal.expense_category_id
                = OLD.expense_category_id

        ) THEN

            RAISE EXCEPTION USING
                ERRCODE = '23514',
                CONSTRAINT = 'ck_expense_reversal_required',
                MESSAGE = 'Expense reversal requires a matching reversal ledger.';

        END IF;

        RETURN NEW;

    END IF;


    RAISE EXCEPTION USING
        ERRCODE = '23514',
        CONSTRAINT = 'ck_expense_posted_immutable',
        MESSAGE = 'Posted expense records cannot be modified.';

END;

$$;


CREATE TRIGGER trg_expenses_protect_posted

BEFORE UPDATE OR DELETE

ON public.expenses

FOR EACH ROW

EXECUTE FUNCTION public.accounting_protect_posted_expense();

'''


REVERSE_SQL = '''

DROP TRIGGER IF EXISTS
    trg_expenses_protect_posted
ON public.expenses;

DROP FUNCTION IF EXISTS
    public.accounting_protect_posted_expense();


DROP TRIGGER IF EXISTS
    trg_payments_protect_completed
ON public.payments;

DROP FUNCTION IF EXISTS
    public.accounting_protect_completed_payment();

'''


class Migration(migrations.Migration):

    atomic = True

    dependencies = [
        ("accounting", "0014_ledger_source_integrity"),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
