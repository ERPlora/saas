"""Account → Security → «Change password» is allauth.headless's ``account/password/change`` (PLAN-SAAS §6).

Ported from ERPlora/saas ``apps/dashboard/profile/tests/test_change_password_rate_limit.py`` (10; saas#2545)
and the password cases of ``test_views`` (profile and settings): the current password is asked, the same
validators as everywhere, and one budget of attempts per account (allauth's ``change_password``, 5 a minute), so
an open session is no password-guessing oracle. Added (PLAN-SAAS §2.1): a new password also asks every business
to end the account's sessions there (``signals.sessions_ended``), as Django ends the other sessions here.
Dropped: the three doors of the original (profile page, settings page, DRF view) are one now.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

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
