from contextlib import contextmanager

from django.db import connection, transaction


@contextmanager
def allow_invalid_reversal_fixture():

    database_name = str(
        connection.settings_dict["NAME"]
    )

    if not database_name.startswith("test_"):
        raise RuntimeError(
            "Refusing to modify triggers outside test database."
        )

    if not connection.in_atomic_block:
        raise RuntimeError(
            "Corrupted fixtures require an atomic test."
        )

    with transaction.atomic():

        with connection.cursor() as cursor:

            cursor.execute("SELECT current_database()")

            if cursor.fetchone()[0] != database_name:
                raise RuntimeError(
                    "Test database verification failed."
                )

            cursor.execute("""
                SELECT tgenabled
                FROM pg_trigger
                WHERE tgrelid = 'public.transactions'::regclass
                AND tgname = 'trg_transactions_validate_reversal'
                AND NOT tgisinternal
            """)

            if cursor.fetchone() != ("O",):
                raise RuntimeError(
                    "Expected enabled reversal validation trigger."
                )

            cursor.execute("""
                ALTER TABLE public.transactions
                DISABLE TRIGGER trg_transactions_validate_reversal
            """)

        yield

        with connection.cursor() as cursor:

            cursor.execute("""
                ALTER TABLE public.transactions
                ENABLE TRIGGER trg_transactions_validate_reversal
            """)
