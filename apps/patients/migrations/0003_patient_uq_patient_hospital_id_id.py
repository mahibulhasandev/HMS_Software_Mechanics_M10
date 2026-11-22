
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("patients", "0002_alter_patient_blood_group_and_more"),
    ]

    operations = [
        # Step 1: Composite unique constraint on Patient
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.UniqueConstraint(
                fields=("hospital", "id"),
                name="uq_patient_hospital_id_id",
            ),
        ),

        # Step 2: Enforce same-hospital PatientVisit relationship
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM patient_visits AS pv
                        INNER JOIN patients AS p
                            ON p.id = pv.patient_id
                        WHERE pv.hospital_id IS DISTINCT FROM p.hospital_id
                    ) THEN
                        RAISE EXCEPTION
                            'Cannot add composite FK: existing PatientVisit records have mismatched hospitals.';
                    END IF;
                END
                $$;

                ALTER TABLE patient_visits
                ADD CONSTRAINT fk_visit_patient_same_hospital
                FOREIGN KEY (hospital_id, patient_id)
                REFERENCES patients (hospital_id, id)
                ON UPDATE NO ACTION
                ON DELETE NO ACTION;
            """,
            reverse_sql="""
                ALTER TABLE patient_visits
                DROP CONSTRAINT IF EXISTS fk_visit_patient_same_hospital;
            """,
        ),
    ]
