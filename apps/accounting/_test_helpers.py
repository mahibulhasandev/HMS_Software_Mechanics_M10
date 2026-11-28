from django.contrib.auth import get_user_model


def create_test_user(*args, **kwargs):
    """
    Create a test user compatible with both auth.User
    and the custom core.User model.
    """

    User = get_user_model()
    kwargs = dict(kwargs)

    if User.USERNAME_FIELD == "username":
        if not args and "username" not in kwargs:
            email = kwargs.get("email")

            if not email:
                raise ValueError(
                    "An email is required for test user creation."
                )

            kwargs["username"] = email

    return User.objects.create_user(*args, **kwargs)
