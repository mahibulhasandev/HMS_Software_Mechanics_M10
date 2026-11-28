import uuid

from django.db import migrations, models


def populate_actor_uuids(apps, schema_editor):
    Membership = apps.get_model("accounting", "AccountingMembership")
    database = schema_editor.connection.alias

    for membership in Membership.objects.using(database).filter(
        actor_uuid__isnull=True
    ).iterator():
        Membership.objects.using(database).filter(
            pk=membership.pk
        ).update(actor_uuid=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0009_accountingmembership_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountingmembership",
            name="actor_uuid",
            field=models.UUIDField(
                null=True,
                editable=False,
            ),
        ),
        migrations.RunPython(
            populate_actor_uuids,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="accountingmembership",
            name="actor_uuid",
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
            ),
        ),
    ]
