import uuid

from django.db import models


class DoctorSchedule(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    hospital = models.ForeignKey(
        "hospitals.Hospital",
        on_delete=models.CASCADE,
        related_name="doctor_schedules",
    )

    doctor = models.ForeignKey(
        "doctors.Doctor",
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    weekday = models.PositiveSmallIntegerField()

    start_time = models.TimeField()
    end_time = models.TimeField()

    slot_minutes = models.PositiveSmallIntegerField()
    max_patients = models.PositiveIntegerField()

    valid_from = models.DateField()
    valid_to = models.DateField()

    class Meta:
        db_table = "doctor_schedules"
        ordering = ["weekday", "start_time"]
        indexes = [
            models.Index(
                fields=["hospital", "doctor", "weekday"],
                name="clinic_doc_sched_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0, weekday__lte=6),
                name="clinic_weekday_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="clinic_schedule_time_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(slot_minutes__gt=0),
                name="clinic_slot_minutes_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(max_patients__gt=0),
                name="clinic_max_patients_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(valid_to__gte=models.F("valid_from")),
                name="clinic_schedule_date_valid",
            ),
        ]

    def __str__(self):
        return (
            f"{self.doctor} - "
            f"Weekday {self.weekday} "
            f"({self.start_time} - {self.end_time})"
        )
