from django.db import connection, transaction
from django.http import JsonResponse

from .models import AccountingMembership


class AccountingHospitalContextMiddleware:
    PREFIX = "/api/accounting/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not (
            request.path == "/api/accounting"
            or request.path.startswith(self.PREFIX)
        ):
            return self.get_response(request)

        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated or not user.is_active:
            return JsonResponse(
                {"detail": "Authentication required."},
                status=401,
            )

        with transaction.atomic():
            try:
                # Inner savepoint ensures database errors can roll back
                # before the cleanup queries execute.
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL ROLE hms_app")
                        cursor.execute(
                            "SELECT set_config('app.user_id', %s, true)",
                            [str(user.pk)],
                        )

                    membership = (
                        AccountingMembership.objects
                        .filter(user_id=user.pk, is_active=True)
                        .first()
                    )

                    if membership is None:
                        return JsonResponse(
                            {"detail": "Accounting access denied."},
                            status=403,
                        )

                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('app.hospital_id', %s, true)",
                            [str(membership.hospital_id)],
                        )

                    request.accounting_hospital_id = membership.hospital_id
                    request.accounting_role = membership.role

                    return self.get_response(request)

            finally:
                with connection.cursor() as cursor:
                    cursor.execute("RESET ROLE")
                    cursor.execute(
                        "SELECT set_config('app.user_id', '', true)"
                    )
                    cursor.execute(
                        "SELECT set_config('app.hospital_id', '', true)"
                    )
