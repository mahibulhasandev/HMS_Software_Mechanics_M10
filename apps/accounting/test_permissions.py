from types import SimpleNamespace
from uuid import uuid4

from django.test import RequestFactory, SimpleTestCase

from apps.accounting.models import AccountingMembership
from apps.accounting.permissions import AccountingRolePermission


class AccountingPermissionTests(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.permission = AccountingRolePermission()
        self.hospital_id = uuid4()

    def make_request(
        self,
        method="GET",
        role="accountant",
        hospital_id=None,
        authenticated=True,
        active=True,
    ):
        request = self.factory.generic(
            method, "/api/accounting/accounts/"
        )
        request.user = SimpleNamespace(
            is_authenticated=authenticated,
            is_active=active,
        )
        request.accounting_role = role
        request.accounting_hospital_id = (
            self.hospital_id
            if hospital_id is None
            else hospital_id
        )
        return request

    def test_all_roles_can_read(self):
        for role in AccountingMembership.Role.values:
            with self.subTest(role=role):
                request = self.make_request(role=role)
                self.assertTrue(
                    self.permission.has_permission(request, None)
                )

    def test_admin_and_accountant_can_write(self):
        for role in ("admin", "accountant"):
            for method in ("POST", "PUT", "PATCH"):
                with self.subTest(role=role, method=method):
                    request = self.make_request(method, role)
                    self.assertTrue(
                        self.permission.has_permission(request, None)
                    )

    def test_staff_cannot_write(self):
        for method in ("POST", "PUT", "PATCH"):
            with self.subTest(method=method):
                request = self.make_request(method, "staff")
                self.assertFalse(
                    self.permission.has_permission(request, None)
                )

    def test_delete_denied_for_every_role(self):
        for role in AccountingMembership.Role.values:
            with self.subTest(role=role):
                request = self.make_request("DELETE", role)
                self.assertFalse(
                    self.permission.has_permission(request, None)
                )

    def test_unauthenticated_and_inactive_users_denied(self):
        for authenticated, active in (
            (False, True),
            (True, False),
        ):
            request = self.make_request(
                authenticated=authenticated,
                active=active,
            )
            self.assertFalse(
                self.permission.has_permission(request, None)
            )

    def test_missing_membership_context_denied(self):
        request = self.make_request()
        request.accounting_hospital_id = None

        self.assertFalse(
            self.permission.has_permission(request, None)
        )

        request = self.make_request(role=None)

        self.assertFalse(
            self.permission.has_permission(request, None)
        )

    def test_cross_hospital_object_access_denied(self):
        request = self.make_request()

        own_account = SimpleNamespace(
            hospital_id=self.hospital_id
        )
        other_account = SimpleNamespace(
            hospital_id=uuid4()
        )

        self.assertTrue(
            self.permission.has_object_permission(
                request, None, own_account
            )
        )

        self.assertFalse(
            self.permission.has_object_permission(
                request, None, other_account
            )
        )
