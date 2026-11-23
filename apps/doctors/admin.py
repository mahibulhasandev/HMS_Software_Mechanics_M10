
from django.contrib import admin
from .models import Doctor, DoctorDepartment, DoctorSpecialization


@admin.register(DoctorDepartment)
class DoctorDepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'hospital', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(DoctorSpecialization)
class DoctorSpecializationAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'hospital', 'is_active')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'department__name')


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = (
        'doctor_code',
        'first_name',
        'last_name',
        'department',
        'specialization',
        'phone',
        'status',
    )
    list_filter = ('status', 'employment_type', 'department')
    search_fields = (
        'doctor_code',
        'first_name',
        'last_name',
        'phone',
        'email',
        'registration_number',
    )
