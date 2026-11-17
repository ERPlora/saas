"""ACCOUNTS-F01: a sign-up whose code cannot be mailed answers a handled 503, never a 500 (saas#391).

Production SES stayed in the sandbox: mailing a code to an unverified address raised out of allauth's view and the
browser got an HTML 500. The answer is now allauth's own error envelope with the code ``mail_unavailable``.
"""

import logging

import pytest
from django.core.mail import EmailMultiAlternatives
from django.test import Client

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
BROWSER = "/_allauth/browser/v1"


class SandboxRejected(Exception):
    """Stands for botocore's ClientError («Email address is not verified»)."""


@pytest.fixture
def mail_cannot_leave(monkeypatch):
    def refuse(self, *args, **kwargs):
        raise SandboxRejected("Email address is not verified")

    monkeypatch.setattr(EmailMultiAlternatives, "send", refuse)


def _sign_up(client, email="new@example.com"):
    return client.post(
        f"{BROWSER}/auth/signup",
        {"email": email, "password": "a long pass phrase 2026"},
        content_type="application/json",
        HTTP_HOST=HOST,
    )


def test_a_signup_whose_code_cannot_be_mailed_is_a_503_with_a_code(mail_cannot_leave, caplog):
    client = Client(raise_request_exception=False)

    with caplog.at_level(logging.ERROR):
        response = _sign_up(client)

    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    assert body["status"] == 503
    assert [error["code"] for error in body["errors"]] == ["mail_unavailable"]
    assert "accounts.mail_failed" in caplog.text
    assert "a long pass phrase" not in caplog.text


def test_a_signup_that_can_be_mailed_is_untouched(client):
    response = _sign_up(client)

    assert response.status_code == 401
    assert [flow["id"] for flow in response.json()["data"]["flows"] if flow.get("is_pending")] == ["verify_email"]
