from django.db import migrations


CONSTRAINT_NAME = "ck_inv_item_status_valid"


def ensure_invoice_item_status_constraint(apps, schema_editor):
    InvoiceItem = apps.get_model("accounting", "InvoiceItem")
    table_name = InvoiceItem._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        existing_constraints = (
            schema_editor.connection.introspection.get_constraints(
                cursor,
                table_name,
            )
        )

    if CONSTRAINT_NAME in existing_constraints:
        return

    constraint = next(
        constraint
        for constraint in InvoiceItem._meta.constraints
        if constraint.name == CONSTRAINT_NAME
    )
    schema_editor.add_constraint(InvoiceItem, constraint)


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0001_initial"),
    ]

    operations = [
        # The constraint is already part of 0001 on the develop line.
        # Earlier accounting databases may have applied 0001 without it.
        # Ensure the database has it without duplicating migration state.
        migrations.RunPython(
            ensure_invoice_item_status_constraint,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
