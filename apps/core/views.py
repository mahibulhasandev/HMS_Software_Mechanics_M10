from django.contrib.auth import login, logout, get_user_model, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models import (
    Department,
    Employee,
    EmployeeRole,
    EmploymentStatus,
    ApprovalStatus,
)
from apps.core.serializers import (
    LoginSerializer,
    UserProfileSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    DepartmentSerializer,
    EmployeeSerializer,
    EmployeeRegistrationSerializer,
    EmployeeStatusUpdateSerializer,
)
from apps.core.permissions import IsHospitalAdmin, IsHospitalStaff, IsHospitalAdminOrReadOnlyStaff

User = get_user_model()


# ==============================================================================
# AUTHENTICATION VIEWS
# ==============================================================================

from rest_framework.authentication import SessionAuthentication

class LoginView(APIView):
    """
    POST /api/auth/login/
    Accepts email or phone with password. Authenticates via custom backend
    and establishes a secure session / returns user profile.
    """
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        # Trigger authentication to enforce CSRF on unsafe methods
        _ = request.user
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Log user into session
        login(request, user)

        # Include summary of active hospital employment profiles
        employments = Employee.objects.filter(
            user=user,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).values("hospital_id", "hospital__name", "role", "designation")

        return Response(
            {
                "message": "Login successful.",
                "user": UserProfileSerializer(user).data,
                "employments": list(employments),
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Flushes user session and logs user out securely.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(
            {"message": "Logged out successfully."},
            status=status.HTTP_200_OK,
        )


class UserProfileView(APIView):
    """
    GET /api/auth/me/
    Returns the authenticated user's profile and active hospital contracts.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employments = Employee.objects.filter(
            user=request.user,
        ).select_related("hospital", "department").values(
            "id",
            "hospital_id",
            "hospital__name",
            "department__name",
            "employee_id",
            "designation",
            "role",
            "employment_status",
            "approval_status",
        )

        return Response({
            "user": UserProfileSerializer(request.user).data,
            "employments": list(employments),
        })


class PasswordChangeView(APIView):
    """
    POST /api/auth/password/change/
    Requires current password and new valid password.
    Updates the session auth hash so the current session remains valid and secure.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        update_session_auth_hash(request, user)
        return Response(
            {"message": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password/reset/request/
    Dispatches a secure token to user email. Always returns 200 to prevent user enumeration.
    If the account exists but has no email (phone-only user), self-service reset is not available
    and must be handled via hospital administrator verification.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email__iexact=email).first()
        if user and user.is_active:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            # Send email via Django configured backend (console in dev)
            send_mail(
                subject="HMS Password Reset",
                message=f"Use token: {token} and UID: {uid} to reset your password.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@hms.local"),
                recipient_list=[user.email],
                fail_silently=True,
            )

        return Response(
            {"message": "If an active account exists with this email, password reset instructions have been sent."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password/reset/confirm/
    Accepts uid, token, and new_password.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        uidb64 = request.data.get("uid")
        token = request.data.get("token")

        if not uidb64 or not token:
            return Response(
                {"detail": "UID and token are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"detail": "Invalid reset link or user ID."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"detail": "Token is invalid or has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PasswordResetConfirmSerializer(
            data=request.data,
            context={"user": user},
        )
        serializer.is_valid(raise_exception=True)

        user.set_password(serializer.validated_data["new_password"])
        user.save()

        return Response(
            {"message": "Password has been successfully reset. You can now log in with your new password."},
            status=status.HTTP_200_OK,
        )


# ==============================================================================
# DEPARTMENT & EMPLOYEE MANAGEMENT VIEWS
# ==============================================================================

class DepartmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for Departments within a hospital.
    - Read (list, retrieve): Accessible to active approved Hospital Staff.
    - Write (create, update, partial_update, destroy): Accessible strictly to Hospital Admins.
    """
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, IsHospitalAdminOrReadOnlyStaff]

    def get_queryset(self):
        qs = Department.objects.select_related("hospital").all()
        hospital_id = (
            self.request.headers.get("X-Hospital-ID")
            or self.request.query_params.get("hospital")
        )
        if hospital_id:
            qs = qs.filter(hospital_id=hospital_id)
        elif not self.request.user.is_superuser:
            # Filter to hospitals where user has active approved employment
            user_hospitals = self.request.user.employee_profiles.filter(
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).values_list("hospital_id", flat=True)
            qs = qs.filter(hospital_id__in=user_hospitals)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        target_hospital = serializer.validated_data.get("hospital")

        if not target_hospital:
            raise ValidationError({"hospital": "Hospital is required."})

        if not user.is_superuser:
            is_admin = Employee.objects.filter(
                user=user,
                hospital=target_hospital,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()
            if not is_admin:
                raise PermissionDenied("You are not an authorized administrator for this hospital.")

        serializer.save()

    def perform_update(self, serializer):
        user = self.request.user
        instance = serializer.instance

        if not user.is_superuser:
            is_admin = Employee.objects.filter(
                user=user,
                hospital=instance.hospital,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()
            if not is_admin:
                raise PermissionDenied("You are not an authorized administrator for this hospital.")

        serializer.save()

    def perform_destroy(self, instance):
        user = self.request.user
        if not user.is_superuser:
            is_admin = Employee.objects.filter(
                user=user,
                hospital=instance.hospital,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()
            if not is_admin:
                raise PermissionDenied("You are not an authorized administrator for this hospital.")

        instance.delete()


class EmployeeViewSet(viewsets.ModelViewSet):
    """
    Enterprise Employee Management API.
    - POST /register/: Submit an employment registration request (Pending).
    - GET /: List employees (Scoped to hospital).
    - POST /{id}/approve/: Approve employee (Hospital Admin only, same hospital, no self-approval).
    - POST /{id}/reject/: Reject employee registration (Hospital Admin only).
    - PATCH /{id}/update_status/: Change designation, department, employment status (Hospital Admin only).
    """
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Employee.objects.select_related("user", "hospital", "department", "approved_by__user").all()

        hospital_id = (
            self.request.headers.get("X-Hospital-ID")
            or self.request.query_params.get("hospital")
        )

        if user.is_superuser:
            if hospital_id:
                return qs.filter(hospital_id=hospital_id)
            return qs

        if hospital_id:
            # Verify user has approved employment in this hospital
            user_emp = Employee.objects.filter(
                user=user,
                hospital_id=hospital_id,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).first()

            if not user_emp:
                # If user has a pending application here, they can only see their own application
                return qs.filter(hospital_id=hospital_id, user=user)

            # If Hospital Admin, sees all staff in this hospital
            if user_emp.role == EmployeeRole.HOSPITAL_ADMIN:
                return qs.filter(hospital_id=hospital_id)

            # Standard staff can only view approved colleagues in their hospital
            return qs.filter(
                hospital_id=hospital_id,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            )

        # No hospital header supplied:
        # If user is Hospital Admin in any hospital, allow access to those hospitals' employees
        admin_hospitals = Employee.objects.filter(
            user=user,
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).values_list("hospital_id", flat=True)

        if admin_hospitals.exists():
            return qs.filter(hospital_id__in=admin_hospitals)

        # Standard staff: return user's own employment profiles
        return qs.filter(user=user)

    def create(self, request, *args, **kwargs):
        """
        Direct creation via POST /api/employees/ is restricted to Hospital Admins or Superusers.
        Regular applicants must use POST /api/employees/register/.
        """
        target_hospital_id = request.data.get("hospital")
        if not target_hospital_id:
            raise ValidationError({"hospital": "Hospital is required."})

        if not request.user.is_superuser:
            is_admin = Employee.objects.filter(
                user=request.user,
                hospital_id=target_hospital_id,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).exists()
            if not is_admin:
                raise PermissionDenied(
                    "Direct employee creation requires Hospital Administrator privileges. "
                    "Standard applicants must use /api/employees/register/."
                )

        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="register")
    def register(self, request):
        """
        POST /api/employees/register/
        Allows authenticated user to apply for an employee position at a hospital.
        Always created as PENDING approval.
        """
        serializer = EmployeeRegistrationSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()

        return Response(
            {
                "message": "Employment registration request submitted successfully. Awaiting Hospital Administrator approval.",
                "employee": EmployeeSerializer(employee).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="approve", permission_classes=[IsAuthenticated, IsHospitalAdmin])
    def approve(self, request, pk=None):
        """
        POST /api/employees/{id}/approve/
        Approves an employee application.
        Strict Rules:
        1. Approver must be an approved Hospital Admin in the SAME hospital.
        2. Cannot approve oneself.
        3. Sets approved_by and approved_at atomically.
        """
        employee = self.get_object()

        # Find approver's admin profile in this employee's hospital
        approver = Employee.objects.filter(
            user=request.user,
            hospital_id=employee.hospital_id,
            role=EmployeeRole.HOSPITAL_ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            employment_status=EmploymentStatus.ACTIVE,
        ).first()

        if not approver and not request.user.is_superuser:
            return Response(
                {"detail": "You must be an active Hospital Administrator in this hospital to approve employees."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prevent self-approval
        if employee.user_id == request.user.id:
            return Response(
                {"detail": "An employee or administrator cannot approve their own registration."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if employee.approval_status == ApprovalStatus.APPROVED:
            return Response(
                {"detail": "This employee is already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            employee.approval_status = ApprovalStatus.APPROVED
            employee.approved_by = approver
            employee.approved_at = timezone.now()
            employee.save()

        return Response(
            {
                "message": f"Employee {employee.employee_id} ({employee.user.full_name}) successfully approved.",
                "employee": EmployeeSerializer(employee).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="reject", permission_classes=[IsAuthenticated, IsHospitalAdmin])
    def reject(self, request, pk=None):
        """
        POST /api/employees/{id}/reject/
        Rejects an employee registration request.
        """
        employee = self.get_object()

        # Check admin role in same hospital
        if not request.user.is_superuser:
            admin_emp = Employee.objects.filter(
                user=request.user,
                hospital_id=employee.hospital_id,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).first()
            if not admin_emp:
                return Response(
                    {"detail": "Only a Hospital Administrator in this hospital can reject applications."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        if employee.user_id == request.user.id:
            return Response(
                {"detail": "You cannot reject your own registration."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            employee.approval_status = ApprovalStatus.REJECTED
            employee.approved_by = None
            employee.approved_at = None
            employee.save()

        return Response(
            {
                "message": f"Employee application {employee.employee_id} has been rejected.",
                "employee": EmployeeSerializer(employee).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["patch"], url_path="status", permission_classes=[IsAuthenticated, IsHospitalAdmin])
    def update_status(self, request, pk=None):
        """
        PATCH /api/employees/{id}/status/
        Updates employee designation, department, role, or employment status (active, on_leave, suspended, etc.).
        """
        employee = self.get_object()

        if not request.user.is_superuser:
            admin_emp = Employee.objects.filter(
                user=request.user,
                hospital_id=employee.hospital_id,
                role=EmployeeRole.HOSPITAL_ADMIN,
                approval_status=ApprovalStatus.APPROVED,
                employment_status=EmploymentStatus.ACTIVE,
            ).first()
            if not admin_emp:
                return Response(
                    {"detail": "Only an administrator in this hospital can update staff status."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = EmployeeStatusUpdateSerializer(
            employee,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "message": "Employee details updated successfully.",
                "employee": EmployeeSerializer(employee).data,
            },
            status=status.HTTP_200_OK,
        )
