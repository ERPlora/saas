"""allauth.headless's doors around an account's addresses and password that the SaaS keeps closed
(``config/urls.py`` mounts these before allauth's own routes; headless only, allauth has no page to close).

- The sign-in email changes only through ``accounts.email.change`` and the code mailed to the new address
  (saas#2536): allauth's API ``/_allauth/browser/v1/account/email`` answers 404, whatever the method (add, make
  primary, remove, resend).
- An account without a password does not get one with the session alone: ``account/password/change`` answers
  403 to it, and «Forgot your password?» (which proves the mailbox) gives it one; an account with a password
  changes it there as before (the current one is asked).

allauth's own sign-up (``auth/signup``) is not one of them: it is the launcher's «Create account» tab.
"""

from allauth.headless.account.views import ChangePasswordView
from allauth.headless.constants import Client
from django.http import JsonResponse
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt

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
