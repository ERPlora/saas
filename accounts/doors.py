"""allauth.headless's doors around an account's addresses and password that the SaaS keeps closed
(``config/urls.py`` mounts these before allauth's own routes; headless only, allauth has no page to close).

- The sign-in email changes only through ``accounts.email.change`` and the code mailed to the new address
  (saas#2536): allauth's API ``/_allauth/browser/v1/account/email`` answers 404, whatever the method (add, make
  primary, remove, resend).
- An account without a password does not get one with the session alone: ``account/password/change`` answers
  403 to it, and «Forgot your password?» (which proves the mailbox) gives it one; an account with a password
  changes it there as before (the current one is asked).

allauth's own sign-up (``auth/signup``) and sign-in (``auth/login``) are not closed: they are the launcher's two
tabs. Each is served here with one rule allauth.headless leaves out: the sign-in's address in the plain form of the
sign-up's (``adapters.plain_email``; allauth folds the sign-up's in the adapter, the sign-in's only here), and the
sign-up's password checked against its own address, as allauth's template sign-up did (ERPlora/saas#2542: no
password like the email; headless checks it without the account, so Django's similarity rule saw nothing).
"""

from allauth.account.adapter import get_adapter
from allauth.headless.account.inputs import LoginInput, SignupInput
from allauth.headless.account.views import ChangePasswordView, LoginView, SignupView
from allauth.headless.constants import Client
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt

from accounts.adapters import plain_email

_allauth_password_change = ChangePasswordView.as_api_view(client=Client.BROWSER)


def _error(status: int, code: str, message: str) -> JsonResponse:
    """An answer in allauth.headless's shape, so its client reads it as one of its own."""
    return JsonResponse({"status": status, "errors": [{"code": code, "message": message}]}, status=status)


@csrf_exempt  # it changes nothing, whatever the method: answering 404 needs no token
def closed(request, *args, **kwargs) -> JsonResponse:
    return _error(404, "not_found", gettext("Not found."))


def password_change(request, *args, **kwargs):
    """allauth.headless's password change, except for an account without a password."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and not user.has_usable_password():
        return _error(
            403,
            "password_required",
            gettext("Your account has no password yet: set one with «Forgot your password?»."),
        )
    return _allauth_password_change(request, *args, **kwargs)


class _PlainEmailLoginInput(LoginInput):
    def clean_email(self) -> str:
        email = self.cleaned_data.get("email")
        return plain_email(email) if email else email


class _LoginView(LoginView):
    input_class = _PlainEmailLoginInput


#: allauth.headless's sign-in, with the address in its plain form (``plain_email``).
login = _LoginView.as_api_view(client=Client.BROWSER)


class _OwnAddressSignupInput(SignupInput):
    def clean(self):
        cleaned = super().clean()
        password, email = cleaned.get("password"), cleaned.get("email")
        if password and email and "password" not in self.errors:
            try:
                get_adapter().clean_password(password, user=get_user_model()(email=email))
            except ValidationError as error:
                self.add_error("password", error)
        return cleaned


class _SignupView(SignupView):
    input_class = {"POST": _OwnAddressSignupInput}


#: allauth.headless's sign-up, with the password checked against the address it signs up.
signup = _SignupView.as_api_view(client=Client.BROWSER)
