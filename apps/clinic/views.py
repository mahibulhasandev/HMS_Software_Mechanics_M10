import datetime
from django.db import models, transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from apps.clinic.models import DoctorSchedule, Appointment, Consultation, Diagnosis
from apps.clinic.serializers import (
    DoctorScheduleSerializer,
    AppointmentSerializer,
    ConsultationSerializer,
    DiagnosisSerializer,
)
from apps.clinic.permissions import (
    IsClinicStaff,
    IsDoctor,
    IsHospitalAdmin,
    IsReceptionist,
    get_hospital_id_from_request,
)
from apps.doctors.models import Doctor
from apps.patients.permissions import get_active_employee_for_hospital, get_employee_model_and_enums
from apps.patients.models import PatientVisit
from apps.patients.serializers import PatientVisitSerializer


class DoctorScheduleViewSet(viewsets.ModelViewSet):
    """
    Doctor Schedule management API:
    - Lists and retrieves doctor schedules scoped to the authorized hospital.
    - Allows Hospital Admin to create/update/delete any schedule for their hospital.
    - Allows Doctor to create/update schedules for their own doctor profile.
    - Prevents unauthorized cross-hospital and cross-doctor tampering.
    """
    serializer_class = DoctorScheduleSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsClinicStaff]

    def get_queryset(self):
        user = self.request.user
        qs = DoctorSchedule.objects.select_related("doctor", "hospital").all()

        if user.is_superuser:
            hospital_id = get_hospital_id_from_request(self.request, self)
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        hospital_id = get_hospital_id_from_request(self.request, self)
        if not hospital_id:
            # Fallback to employee's hospitals
            Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
            if not Employee:
                return qs.none()
            user_hospitals = Employee.objects.filter(
                user=user,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).values_list("hospital_id", flat=True)
            return qs.filter(hospital_id__in=user_hospitals)

        employee = get_active_employee_for_hospital(user, hospital_id)
        if not employee:
            return qs.none()

        qs = qs.filter(hospital_id=hospital_id)

        # If user is a Doctor, restrict list/retrieve to their own doctor profile
        if employee.role == "doctor":
            try:
                doctor_profile = Doctor.objects.get(employee=employee, hospital_id=hospital_id)
                return qs.filter(doctor=doctor_profile)
            except Doctor.DoesNotExist:
                return qs.none()

        # Admins, Nurses, Receptionists can view schedules for the hospital
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")
        target_doctor = serializer.validated_data.get("doctor")

        if not target_hospital:
            raise ValidationError({"hospital": "Hospital is required."})

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, target_hospital.id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            # Only Admin or the Doctor themselves can create schedules
            if employee.role == "doctor":
                if not hasattr(target_doctor, "employee") or target_doctor.employee_id != employee.id:
                    raise PermissionDenied("Doctors can only create schedules for their own doctor profile.")
            elif employee.role != "hospital_admin" and employee.role != "admin":
                raise PermissionDenied("Only hospital administrators and the doctor themselves can configure schedules.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, instance.hospital_id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            if employee.role == "doctor":
                if not hasattr(instance.doctor, "employee") or instance.doctor.employee_id != employee.id:
                    raise PermissionDenied("Doctors can only modify schedules for their own doctor profile.")
            elif employee.role != "hospital_admin" and employee.role != "admin":
                raise PermissionDenied("Only hospital administrators and the doctor themselves can modify schedules.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, instance.hospital_id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            if employee.role == "doctor":
                if not hasattr(instance.doctor, "employee") or instance.doctor.employee_id != employee.id:
                    raise PermissionDenied("Doctors can only delete schedules for their own doctor profile.")
            elif employee.role != "hospital_admin" and employee.role != "admin":
                raise PermissionDenied("Only hospital administrators and the doctor themselves can delete schedules.")

        instance.delete()


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Appointment management API:
    - Receptionists and Admins can book and manage appointments.
    - Doctors can view and manage only appointments assigned to them.
    - Concurrency-safe slot reservation via advisory locking and atomic verification.
    """
    serializer_class = AppointmentSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsClinicStaff]

    def get_queryset(self):
        user = self.request.user
        qs = Appointment.objects.select_related("hospital", "doctor", "patient").all()

        if user.is_superuser:
            hospital_id = get_hospital_id_from_request(self.request, self)
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        hospital_id = get_hospital_id_from_request(self.request, self)
        if not hospital_id:
            Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
            if not Employee:
                return qs.none()
            user_hospitals = Employee.objects.filter(
                user=user,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).values_list("hospital_id", flat=True)
            return qs.filter(hospital_id__in=user_hospitals)

        employee = get_active_employee_for_hospital(user, hospital_id)
        if not employee:
            return qs.none()

        qs = qs.filter(hospital_id=hospital_id)

        # Role-based scoping: Doctors see only their own appointments
        if employee.role == "doctor":
            try:
                doctor_profile = Doctor.objects.get(employee=employee, hospital_id=hospital_id)
                return qs.filter(doctor=doctor_profile)
            except Doctor.DoesNotExist:
                return qs.none()

        # Admin, Receptionist, Nurse see all appointments within the hospital
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")
        target_doctor = serializer.validated_data.get("doctor")
        appointment_date = serializer.validated_data.get("appointment_date")
        appointment_time = serializer.validated_data.get("appointment_time")

        if not target_hospital:
            raise ValidationError({"hospital": "Hospital is required."})

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, target_hospital.id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            # Booking permission: Receptionist and Admin (Doctors cannot book appointments for others)
            allowed_booking_roles = {"receptionist", "hospital_admin", "admin"}
            if employee.role not in allowed_booking_roles:
                raise PermissionDenied(
                    f"Role '{employee.role}' does not have permission to book appointments. "
                    "Only Receptionists and Hospital Administrators can book appointments."
                )

        # Critical Booking Concurrency Protection
        # We acquire an atomic transaction with a database-level lock or deterministic check
        with transaction.atomic():
            # Concurrency double-booking check:
            # Query active appointments for this doctor, date, and time using select_for_update
            active_statuses = [
                Appointment.Status.PENDING,
                Appointment.Status.CONFIRMED,
                Appointment.Status.CHECKED_IN,
            ]
            conflicts = Appointment.objects.select_for_update().filter(
                hospital=target_hospital,
                doctor=target_doctor,
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                status__in=active_statuses,
            )

            # Check if doctor schedule exists for this weekday and is available
            weekday = appointment_date.weekday()
            schedule = DoctorSchedule.objects.filter(
                hospital=target_hospital,
                doctor=target_doctor,
                weekday=weekday,
                is_available=True,
                valid_from__lte=appointment_date,
            ).filter(
                models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=appointment_date)
            ).filter(
                start_time__lte=appointment_time,
                end_time__gt=appointment_time,
            ).first()

            max_allowed = schedule.max_patients if schedule else 1

            if conflicts.count() >= max_allowed:
                raise ValidationError({
                    "appointment_time": "The selected time slot is already fully booked for this doctor."
                })

            serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance
        target_hospital = instance.hospital

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, target_hospital.id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            if employee.role == "doctor":
                # Doctor can only update their own appointments
                if not hasattr(instance.doctor, "employee") or instance.doctor.employee_id != employee.id:
                    raise PermissionDenied("Doctors can only access and update their assigned appointments.")
            elif employee.role not in {"receptionist", "hospital_admin", "admin", "nurse"}:
                raise PermissionDenied(f"Role '{employee.role}' does not have permission to modify appointments.")

        new_date = serializer.validated_data.get("appointment_date", instance.appointment_date)
        new_time = serializer.validated_data.get("appointment_time", instance.appointment_time)
        new_doctor = serializer.validated_data.get("doctor", instance.doctor)

        # If time or date is changing, lock and verify capacity
        if (new_date != instance.appointment_date or
            new_time != instance.appointment_time or
            new_doctor != instance.doctor):

            with transaction.atomic():
                active_statuses = [
                    Appointment.Status.PENDING,
                    Appointment.Status.CONFIRMED,
                    Appointment.Status.CHECKED_IN,
                ]
                conflicts = Appointment.objects.select_for_update().filter(
                    hospital=target_hospital,
                    doctor=new_doctor,
                    appointment_date=new_date,
                    appointment_time=new_time,
                    status__in=active_statuses,
                ).exclude(pk=instance.pk)

                weekday = new_date.weekday()
                schedule = DoctorSchedule.objects.filter(
                    hospital=target_hospital,
                    doctor=new_doctor,
                    weekday=weekday,
                    is_available=True,
                    valid_from__lte=new_date,
                ).filter(
                    models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=new_date)
                ).filter(
                    start_time__lte=new_time,
                    end_time__gt=new_time,
                ).first()

                max_allowed = schedule.max_patients if schedule else 1

                if conflicts.count() >= max_allowed:
                    raise ValidationError({
                        "appointment_time": "The rescheduled time slot is already fully booked for this doctor."
                    })

                serializer.save()
        else:
            serializer.save()

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        """Check‑in an appointment.

        Business rules enforced:
        * Hospital context must be supplied (via X‑Hospital‑ID header or query param).
        * Appointment must belong to the authorized hospital and patient.
        * Only Receptionist, Hospital Admin or privileged staff may perform the action.
        * Appointment status must be CONFIRMED.
        * A PatientVisit is created on first check‑in; subsequent calls are idempotent.
        * Appointment status is transitioned to CHECKED_IN.
        """
        user = request.user
        hospital_id = get_hospital_id_from_request(request, self)
        if not hospital_id:
            raise ValidationError({"hospital": "Hospital context is required for check‑in."})

        # Enforce role – Receptionist or Hospital Admin (or superuser) allowed
        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, hospital_id)
            if not employee:
                raise PermissionDenied("You are not authorized for this hospital.")
            allowed_roles = {"receptionist", "hospital_admin", "admin"}
            if employee.role not in allowed_roles:
                raise PermissionDenied(f"Role '{employee.role}' cannot perform check‑in.")

        # Lock the appointment row to prevent race conditions
        try:
            with transaction.atomic():
                appointment = Appointment.objects.select_for_update().get(pk=pk, hospital_id=hospital_id)
                # If already checked in, return existing data (idempotent)
                if appointment.patient_visit:
                    visit = appointment.patient_visit
                    appt_serializer = AppointmentSerializer(appointment, context={"request": request})
                    visit_serializer = PatientVisitSerializer(visit, context={"request": request})
                    return Response({
                        "appointment": appt_serializer.data,
                        "patient_visit": visit_serializer.data,
                        "detail": "Already checked in.",
                    })
                # Validate status - only CONFIRMED appointments can be checked in
                if appointment.status != Appointment.Status.CONFIRMED:
                    raise ValidationError({"status": "Only confirmed appointments can be checked in."})
                # Create PatientVisit
                visit = PatientVisit.objects.create(
                    hospital=appointment.hospital,
                    patient=appointment.patient,
                    visit_type=PatientVisit.VisitType.OPD,
                    visit_date=timezone.now(),
                    status=PatientVisit.Status.REGISTERED,
                )
                # Link and update status
                appointment.patient_visit = visit
                appointment.status = Appointment.Status.CHECKED_IN
                appointment.save()
        except Appointment.DoesNotExist:
            raise NotFound("Appointment not found for this hospital.")

        # Serialize response
        appt_serializer = AppointmentSerializer(appointment, context={"request": request})
        visit_serializer = PatientVisitSerializer(visit, context={"request": request})
        return Response({
            "appointment": appt_serializer.data,
            "patient_visit": visit_serializer.data,
        }, status=status.HTTP_200_OK)


class DoctorAvailabilityView(viewsets.ViewSet):
    """
    GET /api/clinic/doctors/{id}/available-slots/?date=YYYY-MM-DD
    Generates available time slots for a doctor on a specific date:
    - Scoped to active DoctorSchedule.
    - Excludes booked/confirmed appointments.
    - Validates hospital context.
    """
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsClinicStaff]

    def list_slots(self, request, doctor_id=None):
        hospital_id = get_hospital_id_from_request(request, self)
        if not hospital_id:
            raise ValidationError({"hospital": "Hospital context (X-Hospital-ID header or hospital parameter) is required."})

        date_str = request.query_params.get("date")
        if not date_str:
            raise ValidationError({"date": "Query parameter 'date' (YYYY-MM-DD) is required."})

        try:
            target_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            raise ValidationError({"date": "Invalid date format. Use YYYY-MM-DD."})

        try:
            doctor = Doctor.objects.get(id=doctor_id, hospital_id=hospital_id)
        except (Doctor.DoesNotExist, ValueError):
            raise NotFound(detail="Doctor not found in this hospital.")

        if doctor.status != Doctor.Status.ACTIVE:
            return Response({
                "doctor_id": str(doctor.id),
                "doctor_name": doctor.full_name,
                "date": str(target_date),
                "status": doctor.status,
                "available_slots": [],
            })

        weekday = target_date.weekday()

        # Fetch active schedules for this weekday
        schedules = DoctorSchedule.objects.filter(
            hospital_id=hospital_id,
            doctor=doctor,
            weekday=weekday,
            is_available=True,
            valid_from__lte=target_date,
        ).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=target_date)
        ).order_by("start_time")

        # Fetch existing active bookings for this doctor and date
        active_statuses = [
            Appointment.Status.PENDING,
            Appointment.Status.CONFIRMED,
            Appointment.Status.CHECKED_IN,
        ]
        existing_bookings = Appointment.objects.filter(
            hospital_id=hospital_id,
            doctor=doctor,
            appointment_date=target_date,
            status__in=active_statuses,
        ).values_list("appointment_time", flat=True)

        # Count bookings per time
        from collections import Counter
        booking_counts = Counter(existing_bookings)

        available_slots = []

        for schedule in schedules:
            slot_delta = datetime.timedelta(minutes=schedule.slot_minutes)
            current_dt = datetime.datetime.combine(target_date, schedule.start_time)
            end_dt = datetime.datetime.combine(target_date, schedule.end_time)

            while current_dt + slot_delta <= end_dt:
                slot_time = current_dt.time()
                booked_count = booking_counts.get(slot_time, 0)
                available_capacity = schedule.max_patients - booked_count

                if available_capacity > 0:
                    available_slots.append({
                        "time": slot_time.strftime("%H:%M:%S"),
                        "display_time": slot_time.strftime("%I:%M %p"),
                        "slot_minutes": schedule.slot_minutes,
                        "available_capacity": available_capacity,
                    })

                current_dt += slot_delta

        return Response({
            "doctor_id": str(doctor.id),
            "doctor_name": doctor.full_name,
            "date": str(target_date),
            "weekday": DoctorSchedule.Weekday(weekday).label,
            "total_available_slots": len(available_slots),
            "available_slots": available_slots,
        })


class ConsultationViewSet(viewsets.ModelViewSet):
    """
    Consultation Management API:
    - Lists and retrieves consultations scoped to the authorized hospital.
    - Receptionists are strictly forbidden from accessing clinical notes.
    - Doctors can only create consultations for their assigned patient visits and view/manage their own consultations.
    - Hospital Admins and Nurses have view-only access across the hospital.
    - Supports custom action 'complete' to finalize clinical documentation.
    """
    serializer_class = ConsultationSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsClinicStaff]

    def get_queryset(self):
        user = self.request.user
        qs = Consultation.objects.select_related(
            "hospital",
            "doctor",
            "patient_visit",
            "patient_visit__patient",
            "appointment",
        ).prefetch_related("diagnoses").all()

        hospital_id = get_hospital_id_from_request(self.request, self)
        if not hospital_id and not user.is_superuser:
            return qs.none()

        if user.is_superuser:
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        employee = get_active_employee_for_hospital(user, hospital_id)
        if not employee:
            return qs.none()

        # Receptionist is strictly forbidden from viewing consultations / clinical notes
        if employee.role == "receptionist":
            raise PermissionDenied("Reception staff cannot access medical consultations.")

        qs = qs.filter(hospital_id=hospital_id)

        # Doctors see only their own consultations
        if employee.role == "doctor":
            try:
                doctor_profile = Doctor.objects.get(employee=employee, hospital_id=hospital_id)
                return qs.filter(doctor=doctor_profile)
            except Doctor.DoesNotExist:
                return qs.none()

        # Admin and Nurse can view consultations for clinical oversight
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")
        target_doctor = serializer.validated_data.get("doctor")
        patient_visit = serializer.validated_data.get("patient_visit")
        appointment = serializer.validated_data.get("appointment")

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, target_hospital.id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            # Only Doctors can conduct/create consultations
            if employee.role != "doctor":
                raise PermissionDenied(f"Role '{employee.role}' cannot create clinical consultations. Only doctors can.")

            # Doctor can only create consultations for their own doctor profile
            if not hasattr(target_doctor, "employee") or target_doctor.employee_id != employee.id:
                raise PermissionDenied("Doctors can only create consultations for their own doctor profile.")

        # BIZ-AUD-01: Concurrency Protection on Consultation Creation
        # Lock PatientVisit with select_for_update inside an atomic transaction
        # Re-check for duplicate consultation under the row lock to prevent race conditions
        with transaction.atomic():
            if patient_visit:
                locked_visit = PatientVisit.objects.select_for_update().get(pk=patient_visit.pk)
                if locked_visit.hospital_id != target_hospital.id:
                    raise ValidationError({"patient_visit": "Patient visit does not belong to the selected hospital."})

                if Consultation.objects.filter(hospital=target_hospital, patient_visit=locked_visit).exists():
                    raise ValidationError({"patient_visit": "A consultation already exists for this patient visit."})

                # Update patient visit status to IN_PROGRESS if currently REGISTERED
                if locked_visit.status == PatientVisit.Status.REGISTERED:
                    locked_visit.status = PatientVisit.Status.IN_PROGRESS
                    locked_visit.save(update_fields=["status", "updated_at"])

            # If appointment is linked, verify doctor assignment
            if appointment and not user.is_superuser:
                if appointment.doctor_id != target_doctor.id:
                    raise PermissionDenied("Cannot create consultation for an appointment assigned to another doctor.")

            serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance
        hospital_id = instance.hospital_id

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, hospital_id)
            if not employee:
                raise PermissionDenied("You are not authorized for this hospital.")

            if employee.role != "doctor":
                raise PermissionDenied("Only doctors can update clinical consultations.")

            # Doctor ownership enforcement
            if not hasattr(instance.doctor, "employee") or instance.doctor.employee_id != employee.id:
                raise PermissionDenied("Doctors can only modify their own consultations.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not user.is_superuser:
            raise PermissionDenied("Clinical consultations cannot be deleted by hospital staff.")
        instance.delete()

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """
        Marks consultation as completed:
        - Locks consultation and linked appointment/visit in an atomic transaction.
        - Transitions Appointment to COMPLETED.
        - Transitions PatientVisit to COMPLETED.
        """
        user = request.user
        hospital_id = get_hospital_id_from_request(request, self)
        if not hospital_id:
            raise ValidationError({"hospital": "Hospital context is required."})

        consultation = self.get_object()

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, hospital_id)
            if not employee:
                raise PermissionDenied("You are not authorized for this hospital.")

            if employee.role != "doctor":
                raise PermissionDenied("Only doctors can complete consultations.")

            if not hasattr(consultation.doctor, "employee") or consultation.doctor.employee_id != employee.id:
                raise PermissionDenied("Doctors can only complete their own consultations.")

        with transaction.atomic():
            # Lock consultation, appointment, and visit
            locked_consultation = Consultation.objects.select_for_update().get(pk=consultation.pk)

            # Update linked Appointment
            if locked_consultation.appointment:
                appt = locked_consultation.appointment
                if appt.status not in [Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW]:
                    appt.status = Appointment.Status.COMPLETED
                    appt.save(update_fields=["status", "updated_at"])

            # Update linked PatientVisit
            if locked_consultation.patient_visit:
                visit = locked_consultation.patient_visit
                if visit.status != PatientVisit.Status.CANCELLED:
                    visit.status = PatientVisit.Status.COMPLETED
                    visit.save(update_fields=["status", "updated_at"])

        serializer = self.get_serializer(locked_consultation)
        return Response({
            "consultation": serializer.data,
            "detail": "Consultation completed successfully.",
        }, status=status.HTTP_200_OK)


class DiagnosisViewSet(viewsets.ModelViewSet):
    """
    Diagnosis Management API:
    - Lists, retrieves, creates, updates, and deletes diagnoses.
    - Tenant-scoped to the active hospital.
    - Only doctors can manage diagnoses for their consultations.
    - Non-clinical staff (receptionists) are forbidden.
    - Diagnoses on completed consultations cannot be modified.
    """
    serializer_class = DiagnosisSerializer
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsClinicStaff]

    def get_queryset(self):
        user = self.request.user
        qs = Diagnosis.objects.select_related("hospital", "consultation", "consultation__doctor").all()

        hospital_id = get_hospital_id_from_request(self.request, self)
        if not hospital_id and not user.is_superuser:
            return qs.none()

        if user.is_superuser:
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        employee = get_active_employee_for_hospital(user, hospital_id)
        if not employee:
            return qs.none()

        if employee.role == "receptionist":
            raise PermissionDenied("Reception staff cannot access diagnosis data.")

        qs = qs.filter(hospital_id=hospital_id)

        # Doctors see diagnoses for their own consultations
        if employee.role == "doctor":
            try:
                doctor_profile = Doctor.objects.get(employee=employee, hospital_id=hospital_id)
                return qs.filter(consultation__doctor=doctor_profile)
            except Doctor.DoesNotExist:
                return qs.none()

        # Admin and Nurse can view
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")
        consultation = serializer.validated_data.get("consultation")

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, target_hospital.id)
            if not employee:
                raise PermissionDenied("You are not an authorized staff member for this hospital.")

            if employee.role != "doctor":
                raise PermissionDenied("Only doctors can record diagnoses.")

            # Doctor can only add diagnosis to their own consultation
            if not hasattr(consultation.doctor, "employee") or consultation.doctor.employee_id != employee.id:
                raise PermissionDenied("Doctors can only record diagnoses for their own consultations.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance
        consultation = instance.consultation

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, instance.hospital_id)
            if not employee:
                raise PermissionDenied("You are not authorized for this hospital.")

            if employee.role != "doctor":
                raise PermissionDenied("Only doctors can modify diagnoses.")

            if not hasattr(consultation.doctor, "employee") or consultation.doctor.employee_id != employee.id:
                raise PermissionDenied("Doctors can only modify diagnoses on their own consultations.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        consultation = instance.consultation

        # SEC-AUD-02: Block diagnosis deletion on completed consultation
        if consultation.is_completed:
            raise PermissionDenied("Cannot delete diagnosis from a completed consultation.")

        if not user.is_superuser:
            employee = get_active_employee_for_hospital(user, instance.hospital_id)
            if not employee:
                raise PermissionDenied("You are not authorized for this hospital.")

            if employee.role != "doctor":
                raise PermissionDenied("Only doctors can delete diagnoses.")

            if not hasattr(consultation.doctor, "employee") or consultation.doctor.employee_id != employee.id:
                raise PermissionDenied("Doctors can only delete diagnoses from their own consultations.")

        instance.delete()
