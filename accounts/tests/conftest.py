"""Fixtures of the accounts tests: an operation context and a browser signed in through allauth."""

import re
import time

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from live.context import OperationContext, Scope
from live.meta import all_live_app_configs, permissions_for_role

from base.operations import ACCOUNT_ROLE

HOST = "localhost:8001"
BROWSER = "/_allauth/browser/v1"
LOGIN = f"{BROWSER}/auth/login"
#: The second step of every password sign-in: the code mailed to the account.
CONFIRM_CODE = f"{BROWSER}/auth/code/confirm"
REAUTHENTICATE = f"{BROWSER}/auth/reauthenticate"
#: Where allauth keeps the sign-ins of a session (``allauth.account.authentication``).
AUTHENTICATION_RECORDS = "account_authentication_methods"


def ctx_for(user, *, request=None, language: str = "en") -> OperationContext:
    """The context a signed-in account gets from a request (``base.operations``)."""
    if user is None:
        return OperationContext(scope=Scope("user", "anonymous"), actor=None, language=language, request=request)
    return OperationContext(
        scope=Scope("user", str(user.pk)),
        actor=user,
        permissions=permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE),
        language=language,
        request=request,
    )


def api_get(client, path, **params):
    return client.get(path, params, HTTP_HOST=HOST)


def api_post(client, path, body=None, **extra):
    return client.post(path, body or {}, content_type="application/json", HTTP_HOST=HOST, **extra)


def prove_address(email: str) -> None:
    """Record ``email`` as proven on its account, as typing the code mailed at sign-up does.

    Every account proves its address before its first session (``ACCOUNT_EMAIL_VERIFICATION``); the code
    itself is ``test_unified_login``'s. The account's other addresses are left as they are.
    """
    user = get_user_model().objects.get(email__iexact=email)
    address = EmailAddress.objects.filter(user=user, email__iexact=email).first()
    if address is None:
        primary = not EmailAddress.objects.filter(user=user, primary=True).exists()
        EmailAddress.objects.create(user=user, email=email.lower(), verified=True, primary=primary)
    elif not address.verified:
        address.verified = True
        address.save(update_fields=["verified"])


def take_mailed_code(email: str) -> str:
    """The six digits of the newest mail to ``email`` (the sign-in code or the one that proves the address),
    taken out of ``mail.outbox`` as the person reads it: a test then counts only the mails of its own steps."""
    for message in reversed(mail.outbox):
        found = re.search(r"^\s*(\d{6})\s*$", message.body, re.MULTILINE)
        if found and email.lower() in (to.lower() for to in message.to):
            mail.outbox.remove(message)
            return found.group(1)
    raise AssertionError(f"no code mailed to {email}")


def sign_in(client, email, password):
    """Sign in as the Vue sign-in does (allauth.headless), with the address proven first (``prove_address``):
    the password, then the code mailed to the account (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``). The session
    records a fresh sign-in."""
    prove_address(email)
    response = client.post(
        LOGIN, {"email": email, "password": password}, content_type="application/json", HTTP_HOST=HOST
    )
    assert response.status_code == 401, response.content
    response = client.post(
        CONFIRM_CODE, {"code": take_mailed_code(email)}, content_type="application/json", HTTP_HOST=HOST
    )
    assert response.status_code == 200, response.content
    return client


def age_sign_in(client, seconds: int = 3600) -> None:
    """Make every sign-in of the client's session ``seconds`` older: past allauth's reauthentication window."""
    session = client.session
    session[AUTHENTICATION_RECORDS] = [
        {**record, "at": record["at"] - seconds} for record in session.get(AUTHENTICATION_RECORDS, [])
    ]
    session.save()


@pytest.fixture
def signed_in(client, ana, password):
    """``ana`` signed in with her password a moment ago: what asks for a recent sign-in lets her through."""
    return sign_in(client, ana.email, password)


@pytest.fixture
def signed_in_long_ago(signed_in):
    """``ana`` signed in an hour ago: deleting the account or creating a key first asks for her password."""
    age_sign_in(signed_in)
    return signed_in


@pytest.fixture
def english(ana):
    """``ana`` reads the panel in English: a signed-in account speaks its own language (``base.language``)."""
    ana.language = "en"
    ana.save(update_fields=["language"])
    return ana


@pytest.fixture
def now():
    return time.time()
