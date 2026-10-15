"""One screen to sign in or sign up: ``POST /_allauth/browser/v1/auth/login`` (ADR-0154 of ERPlora/saas).

The SDK posts ``{email, password}`` to allauth.headless's login address, and this view answers there
(``config/urls.py`` mounts it before allauth's include). An email an account holds
(``accounts.queries.email_has_account``) goes to allauth's own login; any other valid email goes to
allauth's own signup, which creates the account and mails the code that proves the address
(``ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED``, ADR-0159); an invalid one is never looked up, allauth's
login answers it. Nothing of either flow is redone here: the answers, the errors, the CSRF check and the
rate limits (``login``, ``signup``) are allauth's, so the client reads them as before. allauth's own
signup address is closed (``accounts.doors.closed``): this is the one way to create an account with a
password.

Ported from ERPlora/saas ``SubdomainLoginView`` (``apps/auth/users/views.py``), whose implicit sign-up
on the template page becomes the headless signup.
"""

import json

from allauth.headless.account.views import LoginView, SignupView
from allauth.headless.constants import Client
from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponseBase

from accounts import queries

_login = LoginView.as_api_view(client=Client.BROWSER)
_signup = SignupView.as_api_view(client=Client.BROWSER)


def login_or_signup(request: HttpRequest, *args, **kwargs) -> HttpResponseBase:
    """allauth's signup for a ``POST`` with a valid email no account holds; allauth's login for anything else
    (a known email, a missing or invalid one, another method), which answers it as it always did: an
    invalid email is a 400 on ``email`` there, with no query and none of the sign-ups' budget spent."""
    email = _posted_email(request)
    if email and not queries.email_has_account(email):
        return _signup(request, *args, **kwargs)
    return _login(request, *args, **kwargs)


def _posted_email(request: HttpRequest) -> str:
    """The ``email`` of a JSON ``POST`` once Django's ``EmailField`` accepts it, or ``""``: whatever else is
    posted (no email, an invalid one, a NUL character Postgres would refuse) is left to allauth's login, which
    answers it with its own errors (Django keeps the body, so allauth reads it again)."""
    if request.method != "POST":
        return ""
    try:
        data = json.loads(request.body)
    except UnicodeDecodeError, json.JSONDecodeError:
        return ""
    email = data.get("email") if isinstance(data, dict) else None
    try:
        return forms.EmailField().clean(email) if isinstance(email, str) else ""
    except ValidationError:
        return ""
