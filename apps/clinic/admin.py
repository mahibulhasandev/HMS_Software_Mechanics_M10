from django.contrib import admin
from django.utils.html import format_html

from apps.clinic.models import (
    DoctorSchedule,
    Appointment,
    Consultation,
    Diagnosis,
    Prescription,
    PrescriptionItem,
)
from apps.patients.permissions import get_employee_model_and_enums


class BaseHospitalScopedAdmin(admin.ModelAdmin):
    """
    Base ModelAdmin providing multi-tenant queryset scoping in Django Admin.
    - Superusers retain unrestricted global administrative access.
    - Staff users with approved, active Employee membership are strictly scoped
      to their authorized hospital(s).
    - If a user has no approved active employee record, they are prevented from
      viewing cross-hospital records.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs

        Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
        if not Employee:
            return qs

        user_hospitals = Employee.objects.filter(
            user=request.user,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).values_list("hospital_id", flat=True)

        return qs.filter(hospital_id__in=user_hospitals)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Scope foreign key dropdown choices to the user's hospital(s) if not a superuser.
        """
        if not request.user.is_superuser:
            Employee, EmployeeRole, ApprovalStatus, EmploymentStatus = get_employee_model_and_enums()
            if Employee:
                user_hospitals = Employee.objects.filter(
                    user=request.user,
                    approval_status=ApprovalStatus.APPROVED,
                    employment_status=EmploymentStatus.ACTIVE,
                ).values_list("hospital_id", flat=True)

                if db_field.name == "hospital":
                    kwargs["queryset"] = db_field.related_model.objects.filter(id__in=user_hospitals)
                elif hasattr(db_field.related_model, "hospital"):
                    kwargs["queryset"] = db_field.related_model.objects.filter(hospital_id__in=user_hospitals)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ==============================================================================
# INLINE CONFIGURATIONS
# ==============================================================================

class DiagnosisInline(admin.TabularInline):
    """
    Tabular inline for managing Diagnoses directly inside the Consultation page.
    """
    model = Diagnosis
    extra = 1
    fields = ("diagnosis_name", "icd_code", "diagnosis_type", "notes", "hospital")
    autocomplete_fields = ("hospital",)


class PrescriptionItemInline(admin.TabularInline):
    """
    Tabular inline for managing Prescription Items directly inside the Prescription page.
    """
    model = PrescriptionItem
    extra = 1
    fields = (
        "dosage",
        "frequency",
        "duration_days",
        "quantity",
        "instructions",
        "medicine_id",
        "hospital",
    )
    autocomplete_fields = ("hospital",)


class PrescriptionInline(admin.StackedInline):
    """
    Stacked inline for viewing and managing Prescriptions linked to a Consultation.
    """
    model = Prescription
    extra = 0
    show_change_link = True
    fields = ("hospital", "notes", "prescribed_at")
    readonly_fields = ("prescribed_at",)
    autocomplete_fields = ("hospital",)


# ==============================================================================
# 1. DOCTOR SCHEDULE ADMIN
# ==============================================================================

@admin.register(DoctorSchedule)
class DoctorScheduleAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "doctor",
        "hospital",
        "weekday_badge",
        "time_window",
        "slot_minutes",
        "max_patients",
        "validity_period",
        "is_available",
    )
    list_filter = (
        "hospital",
        "weekday",
        "is_available",
        "slot_minutes",
    )
    search_fields = (
        "doctor__first_name",
        "doctor__last_name",
        "doctor__doctor_code",
        "doctor__phone",
        "hospital__name",
    )
    ordering = ("hospital", "weekday", "start_time")
    list_per_page = 25
    list_select_related = ("hospital", "doctor")
    autocomplete_fields = ("hospital", "doctor")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Schedule Ownership",
            {
                "fields": (
                    "id",
                    "hospital",
                    "doctor",
                )
            },
        ),
        (
            "Shift & Time Slots",
            {
                "fields": (
                    "weekday",
                    ("start_time", "end_time"),
                    ("slot_minutes", "max_patients"),
                    "is_available",
                )
            },
        ),
        (
            "Validity Range",
            {
                "fields": (
                    ("valid_from", "valid_to"),
                )
            },
        ),
        (
            "Audit Trail",
            {
                "classes": ("collapse",),
                "fields": (
                    ("created_at", "updated_at"),
                ),
            },
        ),
    )

    @admin.display(description="Weekday", ordering="weekday")
    def weekday_badge(self, obj):
        return obj.get_weekday_display()

    @admin.display(description="Shift Time", ordering="start_time")
    def time_window(self, obj):
        start = obj.start_time.strftime("%I:%M %p") if obj.start_time else ""
        end = obj.end_time.strftime("%I:%M %p") if obj.end_time else ""
        return f"{start} - {end}"

    @admin.display(description="Validity")
    def validity_period(self, obj):
        from_str = str(obj.valid_from) if obj.valid_from else ""
        to_str = str(obj.valid_to) if obj.valid_to else "Ongoing"
        return f"{from_str} to {to_str}"


# ==============================================================================
# 2. APPOINTMENT ADMIN
# ==============================================================================

@admin.register(Appointment)
class AppointmentAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "patient",
        "doctor",
        "hospital",
        "appointment_date",
        "appointment_time",
        "status_badge",
        "booking_source",
        "patient_visit",
    )
    list_filter = (
        "hospital",
        "status",
        "booking_source",
        "appointment_date",
    )
    search_fields = (
        "patient__first_name",
        "patient__last_name",
        "patient__patient_number",
        "patient__phone",
        "doctor__first_name",
        "doctor__last_name",
        "doctor__doctor_code",
        "hospital__name",
        "reason",
    )
    date_hierarchy = "appointment_date"
    ordering = ("-appointment_date", "appointment_time")
    list_per_page = 25
    list_select_related = ("hospital", "patient", "doctor", "patient_visit")
    autocomplete_fields = ("hospital", "patient", "doctor", "patient_visit")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (
            "Appointment Details",
            {
                "fields": (
                    "id",
                    "hospital",
                    "patient",
                    "doctor",
                    "patient_visit",
                )
            },
        ),
        (
            "Schedule & Status",
            {
                "fields": (
                    ("appointment_date", "appointment_time"),
                    ("status", "booking_source"),
                )
            },
        ),
        (
            "Clinical Notes & Reason",
            {
                "fields": (
                    "reason",
                    "cancellation_reason",
                )
            },
        ),
        (
            "Audit Trail",
            {
                "classes": ("collapse",),
                "fields": (
                    ("created_at", "updated_at"),
                ),
            },
        ),
    )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            Appointment.Status.PENDING: "#f39c12",
            Appointment.Status.CONFIRMED: "#27ae60",
            Appointment.Status.CHECKED_IN: "#2980b9",
            Appointment.Status.COMPLETED: "#2c3e50",
            Appointment.Status.CANCELLED: "#c0392b",
            Appointment.Status.NO_SHOW: "#7f8c8d",
        }
        color = colors.get(obj.status, "#333333")
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )


# ==============================================================================
# 3. CONSULTATION ADMIN
# ==============================================================================

@admin.register(Consultation)
class ConsultationAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "id_short",
        "patient_visit",
        "doctor",
        "hospital",
        "appointment",
        "follow_up_date",
        "created_at",
    )
    list_filter = (
        "hospital",
        "created_at",
        "follow_up_date",
    )
    search_fields = (
        "patient_visit__visit_number",
        "patient_visit__patient__first_name",
        "patient_visit__patient__last_name",
        "patient_visit__patient__patient_number",
        "doctor__first_name",
        "doctor__last_name",
        "doctor__doctor_code",
        "hospital__name",
        "complaints",
        "examination_notes",
        "advice",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 25
    list_select_related = ("hospital", "patient_visit", "doctor", "appointment")
    autocomplete_fields = ("hospital", "patient_visit", "doctor", "appointment")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [DiagnosisInline, PrescriptionInline]

    fieldsets = (
        (
            "Consultation Context",
            {
                "fields": (
                    "id",
                    "hospital",
                    "patient_visit",
                    "doctor",
                    "appointment",
                )
            },
        ),
        (
            "Clinical Assessment",
            {
                "fields": (
                    "complaints",
                    "examination_notes",
                    "advice",
                    "follow_up_date",
                )
            },
        ),
        (
            "Audit Trail",
            {
                "classes": ("collapse",),
                "fields": (
                    ("created_at", "updated_at"),
                ),
            },
        ),
    )

    @admin.display(description="Consultation ID")
    def id_short(self, obj):
        return f"CONS-{str(obj.id)[:8].upper()}"


# ==============================================================================
# 4. DIAGNOSIS ADMIN
# ==============================================================================

@admin.register(Diagnosis)
class DiagnosisAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "diagnosis_name",
        "diagnosis_type",
        "icd_code",
        "consultation",
        "hospital",
        "created_at",
    )
    list_filter = (
        "hospital",
        "diagnosis_type",
        "created_at",
    )
    search_fields = (
        "diagnosis_name",
        "icd_code",
        "consultation__patient_visit__visit_number",
        "consultation__patient_visit__patient__first_name",
        "consultation__patient_visit__patient__last_name",
        "hospital__name",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 25
    list_select_related = ("hospital", "consultation")
    autocomplete_fields = ("hospital", "consultation")
    readonly_fields = ("id", "created_at")

    fieldsets = (
        (
            "Diagnosis Details",
            {
                "fields": (
                    "id",
                    "hospital",
                    "consultation",
                    "diagnosis_name",
                    ("diagnosis_type", "icd_code"),
                    "notes",
                    "created_at",
                )
            },
        ),
    )


# ==============================================================================
# 5. PRESCRIPTION ADMIN
# ==============================================================================

@admin.register(Prescription)
class PrescriptionAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "id_short",
        "consultation",
        "hospital",
        "prescribed_at",
        "item_count",
    )
    list_filter = (
        "hospital",
        "prescribed_at",
    )
    search_fields = (
        "consultation__patient_visit__visit_number",
        "consultation__patient_visit__patient__first_name",
        "consultation__patient_visit__patient__last_name",
        "consultation__doctor__first_name",
        "consultation__doctor__last_name",
        "hospital__name",
        "notes",
    )
    date_hierarchy = "prescribed_at"
    ordering = ("-prescribed_at",)
    list_per_page = 25
    list_select_related = ("hospital", "consultation")
    autocomplete_fields = ("hospital", "consultation")
    readonly_fields = ("id", "prescribed_at")
    inlines = [PrescriptionItemInline]

    fieldsets = (
        (
            "Prescription Header",
            {
                "fields": (
                    "id",
                    "hospital",
                    "consultation",
                    "notes",
                    "prescribed_at",
                )
            },
        ),
    )

    @admin.display(description="Prescription ID")
    def id_short(self, obj):
        return f"RX-{str(obj.id)[:8].upper()}"

    @admin.display(description="Total Items")
    def item_count(self, obj):
        return obj.items.count()


# ==============================================================================
# 6. PRESCRIPTION ITEM ADMIN
# ==============================================================================

@admin.register(PrescriptionItem)
class PrescriptionItemAdmin(BaseHospitalScopedAdmin):
    list_display = (
        "dosage",
        "frequency",
        "duration_days",
        "quantity",
        "prescription",
        "hospital",
        "medicine_id",
    )
    list_filter = (
        "hospital",
        "frequency",
        "duration_days",
    )
    search_fields = (
        "dosage",
        "frequency",
        "instructions",
        "prescription__consultation__patient_visit__visit_number",
        "prescription__consultation__patient_visit__patient__first_name",
        "prescription__consultation__patient_visit__patient__last_name",
        "hospital__name",
    )
    ordering = ("prescription", "id")
    list_per_page = 25
    list_select_related = ("hospital", "prescription")
    autocomplete_fields = ("hospital", "prescription")
    readonly_fields = ("id",)

    fieldsets = (
        (
            "Prescription Item Details",
            {
                "fields": (
                    "id",
                    "hospital",
                    "prescription",
                    "medicine_id",
                    ("dosage", "frequency"),
                    ("duration_days", "quantity"),
                    "instructions",
                )
            },
        ),
    )
