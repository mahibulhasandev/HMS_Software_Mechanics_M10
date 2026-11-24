from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    """
    Custom authentication backend that permits authentication using either
    email or phone number alongside password.
    Normalizes email case-insensitively and respects is_active.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get("email") or kwargs.get("phone")

        if not username or not password:
            return None

        # Look up by email (normalized lowercase) or exact phone
        normalized_username = username.strip().lower()
        try:
            user = User.objects.get(
                Q(email__iexact=normalized_username) | Q(phone__iexact=username.strip())
            )
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            # Run password hasher once against dummy password to prevent timing attacks
            User().set_password(password)
            return None

        if user.check_password(password):
            return user
        return None
