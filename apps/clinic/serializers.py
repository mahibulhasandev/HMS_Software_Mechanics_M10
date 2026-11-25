import datetime
from django.utils import timezone
from rest_framework import serializers

from apps.clinic.models import DoctorSchedule, Appointment
from apps.doctors.models import Doctor
from apps.patients.models import Patient, PatientVisit


class DoctorScheduleSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = DoctorSchedule
        fields = [
            "id",
            "hospital",
            "doctor",
            "doctor_name",
            "weekday",
            "weekday_display",
            "start_time",
            "end_time",
            "slot_minutes",
            "max_patients",
            "valid_from",
            "valid_to",
            "is_available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_slot_minutes(self, value):
        if value not in [15, 30, 45]:
            raise serializers.ValidationError("Slot minutes must be 15, 30, or 45.")
        return value

    def validate_max_patients(self, value):
        if value < 1:
            raise serializers.ValidationError("Max patients must be at least 1.")
        return value

    def validate(self, attrs):
        hospital = attrs.get("hospital", getattr(self.instance, "hospital", None))
        doctor = attrs.get("doctor", getattr(self.instance, "doctor", None))
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        weekday = attrs.get("weekday", getattr(self.instance, "weekday", None))
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(self.instance, "valid_to", None))

        if not hospital:
            raise serializers.ValidationError({"hospital": "Hospital is required."})
        if not doctor:
            raise serializers.ValidationError({"doctor": "Doctor is required."})

        # Doctor ownership and hospital match
        if doctor.hospital_id != hospital.id:
            raise serializers.ValidationError({
                "doctor": "Doctor does not belong to the selected hospital."
            })

        # Doctor status validation
        if doctor.status != Doctor.Status.ACTIVE:
            raise serializers.ValidationError({
                "doctor": f"Doctor status is '{doctor.status}'. Schedules can only be configured for active doctors."
            })

        # Verify linked employee role if linked
        if doctor.employee_id:
            if doctor.employee.role != "doctor":
                raise serializers.ValidationError({
                    "doctor": "Doctor's linked employee profile does not have the 'doctor' role."
                })
            if doctor.employee.employment_status != "active" or doctor.employee.approval_status != "approved":
                raise serializers.ValidationError({
                    "doctor": "Doctor's linked employee profile is not active and approved."
                })

        # Working hours validation
        if start_time and end_time:
            if end_time <= start_time:
                raise serializers.ValidationError({
                    "end_time": "Working hours end_time must be later than start_time."
                })

        # Date range validation
        if valid_from and valid_to:
            if valid_to < valid_from:
                raise serializers.ValidationError({
                    "valid_to": "valid_to cannot be earlier than valid_from."
                })

        # Schedule overlap prevention for the same doctor and weekday
        if doctor and weekday is not None and start_time and end_time and valid_from:
            overlapping_qs = DoctorSchedule.objects.filter(
                hospital=hospital,
                doctor=doctor,
                weekday=weekday,
                is_available=True,
            )
            if self.instance:
                overlapping_qs = overlapping_qs.exclude(pk=self.instance.pk)

            # Check time overlap: start < existing.end AND end > existing.start
            time_overlap = overlapping_qs.filter(
                start_time__lt=end_time,
                end_time__gt=start_time,
            )

            # Check date range overlap
            for sched in time_overlap:
                sched_to = sched.valid_to or datetime.date(9999, 12, 31)
                req_to = valid_to or datetime.date(9999, 12, 31)
                if not (valid_from > sched_to or req_to < sched.valid_from):
                    raise serializers.ValidationError({
                        "non_field_errors": [
                            f"Schedule overlaps with existing schedule on {sched.get_weekday_display()} "
                            f"({sched.start_time.strftime('%H:%M')}-{sched.end_time.strftime('%H:%M')})."
                        ]
                    })

        return attrs


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField(read_only=True)
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "hospital",
            "patient",
            "patient_name",
            "doctor",
            "doctor_name",
            "patient_visit",
            "appointment_date",
            "appointment_time",
            "status",
            "booking_source",
            "reason",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_patient_name(self, obj):
        if obj.patient:
            return f"{obj.patient.first_name} {obj.patient.last_name}".strip()
        return ""

    ALLOWED_TRANSITIONS = {
        Appointment.Status.PENDING: {
            Appointment.Status.CONFIRMED,
            Appointment.Status.CANCELLED,
            Appointment.Status.NO_SHOW,
        },
        Appointment.Status.CONFIRMED: {
            Appointment.Status.CHECKED_IN,
            Appointment.Status.CANCELLED,
            Appointment.Status.NO_SHOW,
        },
        Appointment.Status.CHECKED_IN: {
            Appointment.Status.COMPLETED,
            Appointment.Status.CANCELLED,
        },
        Appointment.Status.COMPLETED: set(),  # Terminal state
        Appointment.Status.CANCELLED: set(),  # Terminal state
        Appointment.Status.NO_SHOW: set(),    # Terminal state
    }

    def validate_appointment_date(self, value):
        if not self.instance and value < timezone.localdate():
            raise serializers.ValidationError("Cannot create appointments in the past.")
        return value

    def validate(self, attrs):
        hospital = attrs.get("hospital", getattr(self.instance, "hospital", None))
        patient = attrs.get("patient", getattr(self.instance, "patient", None))
        doctor = attrs.get("doctor", getattr(self.instance, "doctor", None))
        patient_visit = attrs.get("patient_visit", getattr(self.instance, "patient_visit", None))
        new_status = attrs.get("status", None)

        if not hospital:
            raise serializers.ValidationError({"hospital": "Hospital is required."})
        if not patient:
            raise serializers.ValidationError({"patient": "Patient is required."})
        if not doctor:
            raise serializers.ValidationError({"doctor": "Doctor is required."})

        # Tenant boundary matching
        if patient.hospital_id != hospital.id:
            raise serializers.ValidationError({
                "patient": "Patient does not belong to the selected hospital."
            })
        if doctor.hospital_id != hospital.id:
            raise serializers.ValidationError({
                "doctor": "Doctor does not belong to the selected hospital."
            })

        if patient_visit:
            if patient_visit.hospital_id != hospital.id:
                raise serializers.ValidationError({
                    "patient_visit": "Patient visit does not belong to this hospital."
                })
            if patient_visit.patient_id != patient.id:
                raise serializers.ValidationError({
                    "patient_visit": "Patient visit does not belong to this patient."
                })

        # Validate doctor status
        if doctor.status != Doctor.Status.ACTIVE:
            raise serializers.ValidationError({
                "doctor": f"Doctor status is '{doctor.status}'. Appointments can only be booked for active doctors."
            })

        # State transition validation on update
        if self.instance and new_status and new_status != self.instance.status:
            current_status = self.instance.status
            allowed = self.ALLOWED_TRANSITIONS.get(current_status, set())
            if new_status not in allowed:
                raise serializers.ValidationError({
                    "status": f"Invalid status transition from '{current_status}' to '{new_status}'."
                })

            if new_status == Appointment.Status.CANCELLED:
                cancellation_reason = attrs.get(
                    "cancellation_reason",
                    getattr(self.instance, "cancellation_reason", ""),
                )
                if not cancellation_reason or not cancellation_reason.strip():
                    raise serializers.ValidationError({
                        "cancellation_reason": "Cancellation reason is required when cancelling an appointment."
                    })

        return attrs
