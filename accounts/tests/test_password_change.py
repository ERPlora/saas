"""Account → Security → «Change password» is allauth.headless's ``account/password/change`` (PLAN-SAAS §6).

Ported from ERPlora/saas ``apps/dashboard/profile/tests/test_change_password_rate_limit.py`` (10; saas#2545)
and the password cases of ``test_views`` (profile and settings): the current password is asked, the same
validators as everywhere, and one budget of attempts per account (allauth's ``change_password``, 5 a minute), so
an open session is no password-guessing oracle. Added (PLAN-SAAS §2.1): a new password also asks every business
to end the account's sessions there (``signals.sessions_ended``), as Django ends the other sessions here.
Dropped: the three doors of the original (profile page, settings page, DRF view) are one now.
"""

import pytest
from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import translation

from accounts import signals
from accounts.tests.conftest import BROWSER, HOST, sign_in

pytestmark = pytest.mark.django_db

CHANGE = f"{BROWSER}/account/password/change"
NEW_PASSWORD = "a brand new pass phrase 2026"


def _change(client, current, new=NEW_PASSWORD):
    return client.post(
        CHANGE, {"current_password": current, "new_password": new}, content_type="application/json", HTTP_HOST=HOST
    )


@pytest.fixture
def received():
    calls = []

    def sessions_ended(sender, user_id, **kwargs):
        calls.append(user_id)

    signals.sessions_ended.connect(sessions_ended, dispatch_uid="test-password-ended")
    yield calls
    signals.sessions_ended.disconnect(dispatch_uid="test-password-ended")


def test_the_right_password_changes_it_keeps_this_session_and_ends_the_others(signed_in, ana, password, received):
    phone = sign_in(Client(), ana.email, password)

    response = _change(signed_in, password)

    assert response.status_code == 200
    ana.refresh_from_db()
    assert ana.check_password(NEW_PASSWORD)
    assert signed_in.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 200
    assert phone.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 401
    assert received == [ana.pk]


def test_a_wrong_current_password_changes_nothing(signed_in, ana, received):
    response = _change(signed_in, "not my password")

    assert response.status_code == 400
    assert response.json()["errors"][0]["param"] == "current_password"
    assert received == []


def test_a_weak_new_password_is_refused_as_everywhere(signed_in, password):
    response = _change(signed_in, password, new="12345678")

    assert response.status_code == 400
    assert {error["param"] for error in response.json()["errors"]} == {"new_password"}


def test_the_current_password_is_not_a_new_one(signed_in, ana, password, received):
    """ERPlora/saas#2612 (ACCOUNTS-G42): «new» means new, as the old profile page said and its API did not."""
    response = _change(signed_in, password, new=password)

    assert response.status_code == 400
    [error] = response.json()["errors"]
    assert (error["param"], error["code"]) == ("new_password", "password_unchanged")
    assert received == []


def test_a_reset_to_the_current_password_is_refused_too(client, ana, password):
    """The rule is the account's, whatever the door: the reset's key asks for a password that is not today's."""
    from allauth.account.adapter import get_adapter
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError) as refused:
        get_adapter().clean_password(password, user=ana)

    assert refused.value.code == "password_unchanged"
    assert get_adapter().clean_password(NEW_PASSWORD, user=ana) == NEW_PASSWORD


def test_the_errors_speak_the_accounts_language(signed_in, ana):
    """ERPlora/saas#2614 (ACCOUNTS-G46): Ana reads Spanish, and so do the errors of «Change password»."""
    response = _change(signed_in, "not my password")

    with translation.override("es"):
        expected = str(DefaultAccountAdapter.error_messages["enter_current_password"])
    with translation.override("en"):
        english = str(DefaultAccountAdapter.error_messages["enter_current_password"])
    assert response.json()["errors"][0]["message"] == expected != english


def test_the_unchanged_password_is_said_in_spanish_too(signed_in, password):
    response = _change(signed_in, password, new=password)

    assert response.json()["errors"][0]["message"] == "La contraseña nueva tiene que ser distinta de la actual."


def test_once_the_budget_is_spent_not_even_the_right_password_goes_through(signed_in, ana, password):
    for _ in range(5):
        _change(signed_in, "wrong guess")

    assert _change(signed_in, password).status_code == 429
    ana.refresh_from_db()
    assert ana.check_password(password)


def test_another_account_keeps_its_own_budget(signed_in, password):
    for _ in range(5):
        _change(signed_in, "wrong guess")
    bo = get_user_model().objects.create_user(email="bo@example.com", password=password)

    assert _change(sign_in(Client(), bo.email, password), password).status_code == 200


def test_a_password_set_from_forgot_your_password_also_asks_the_businesses(client, ana, received):
    from allauth.account.signals import password_reset

    password_reset.send(sender=get_user_model(), request=None, user=ana)

    assert received == [ana.pk]
