"""The routes of the panel's assistant (plan 2026-10-30-asistente-saas §4, PLAN-SAAS §23): ``POST
/api/assistant/turn`` (``base.assistant.turn``, a stream), ``GET /api/assistant/usage`` (``base.assistant.usage``)
and ``POST /api/assistant/report`` (``base.assistant.report``), with the same paths and operations as the Hub's, so
the shared panel of ``@erplora/ui`` is configured the same in both. Each one with a session; the account is the
session's, never the payload's.
"""

import json

import pytest
from django.core import mail
from django.utils import timezone
from live.ninja import ensure_api_parity, operation_ids

from assistant import queries, services
from assistant.schemas import Caller
from assistant.services import platform_context
from config.api import api
from hubs.tests.conftest import make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
ROUTES = {
    "base.assistant.turn": ("post", "/api/assistant/turn"),
    "base.assistant.usage": ("get", "/api/assistant/usage"),
    "base.assistant.report": ("post", "/api/assistant/report"),
}


def post(client, path, data):
    return client.post(path, json.dumps(data), content_type="application/json", HTTP_HOST=HOST)


@pytest.fixture
def account(make_user):
    return make_user("lena@example.com", first_name="Lena", language="en")


@pytest.fixture
def signed_in(client, account):
    client.force_login(account)
    return client


def report(**change) -> dict:
    return {
        "message_id": "msg_01",
        "reason": "incorrect",
        "comment": "Not true",
        "question": "How much do I pay?",
        "answer": "You pay 0 euros.",
        **change,
    }


class TestTheRoutes:
    def test_each_route_is_bound_to_its_operation(self):
        assert ensure_api_parity(api) == []
        assert set(ROUTES) <= operation_ids(api)

    def test_openapi_lists_them_with_their_methods(self, client):
        paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]

        for name, (method, path) in ROUTES.items():
            assert paths[path][method]["operationId"] == name

    @pytest.mark.parametrize("name", list(ROUTES))
    def test_without_a_session_each_is_a_401(self, client, name):
        method, path = ROUTES[name]
        bodies = {
            "base.assistant.turn": {"messages": [{"role": "user", "content": "hi"}]},
            "base.assistant.report": report(),
        }
        response = post(client, path, bodies[name]) if method == "post" else client.get(path, HTTP_HOST=HOST)

        assert (response.status_code, response.json()["error"]["code"]) == (401, "unauthorized")

    def test_the_turns_body_stays_in_memory_up_to_the_gateways_ceiling(self):
        from assistant.internal import TURN_BODY_BYTES
        from config.asgi import body_ceiling

        assert body_ceiling({"path": "/api/assistant/turn", "headers": []}) == TURN_BODY_BYTES
        assert body_ceiling({"path": "/api/assistant/usage", "headers": []}) is None


    @pytest.mark.parametrize("name", list(ROUTES))
    def test_an_account_without_the_assistants_permission_gets_a_403(self, signed_in, monkeypatch, name):
        """Each route is its operation's ``permission="assistant.ask"``: without it, the 403 envelope."""
        from live.meta import all_live_app_configs, permissions_for_role

        from base import operations

        granted = permissions_for_role(all_live_app_configs(), operations.ACCOUNT_ROLE) - {"assistant.ask"}
        monkeypatch.setattr(operations, "_permissions", lambda actor: granted)
        method, path = ROUTES[name]
        bodies = {"base.assistant.turn": {"messages": [{"role": "user", "content": "hi"}]}, "base.assistant.report": report()}

        response = post(signed_in, path, bodies[name]) if method == "post" else signed_in.get(path, HTTP_HOST=HOST)

        assert (response.status_code, response.json()["error"]["code"]) == (403, "permission_denied")
        assert not mail.outbox


class TestTheUsage:
    def test_the_account_sees_its_own_month(self, signed_in, account):
        services.message_claim(platform_context(), Caller(user_id=account.pk))
        services.message_claim(platform_context(), Caller(user_id=account.pk))

        response = signed_in.get("/api/assistant/usage", HTTP_HOST=HOST)

        expected = queries.resets_at(queries.month_of(timezone.now())).isoformat().replace("+00:00", "Z")
        assert response.status_code == 200
        assert response.json() == {"used": 2, "limit": 30, "resets_at": expected, "demo": False}

    def test_its_businesses_messages_are_not_its_own(self, signed_in, account, plans):
        from hubs.tests.conftest import create_business

        hub = create_business(account)
        services.message_claim(platform_context(), Caller(hub_id=hub.id, slug=hub.slug))

        assert signed_in.get("/api/assistant/usage", HTTP_HOST=HOST).json()["used"] == 0


class TestTheReport:
    def test_it_reaches_the_support_mailbox_naming_the_account(self, signed_in, account, settings):
        settings.SUPPORT_EMAIL = "support@erplora.test"

        response = post(signed_in, "/api/assistant/report", report())

        assert response.status_code == 200
        assert response.json() == {"sent": True, "duplicate": False}
        [sent] = mail.outbox
        assert sent.to == ["support@erplora.test"]
        assert sent.subject == "[Assistant report] lena@example.com · incorrect"
        assert "Account: lena@example.com" in sent.body
        assert "Not true" in sent.body and "How much do I pay?" in sent.body and "You pay 0 euros." in sent.body

    def test_the_same_answer_reported_twice_mails_once(self, signed_in):
        post(signed_in, "/api/assistant/report", report())

        again = post(signed_in, "/api/assistant/report", report(comment="Again"))

        assert again.json() == {"sent": False, "duplicate": True}
        assert len(mail.outbox) == 1

    def test_a_mail_that_cannot_leave_is_a_503_in_the_panels_words(self, signed_in, monkeypatch):
        def fail(self, *args, **kwargs):
            raise OSError("the mail server is down")

        with monkeypatch.context() as broken:
            broken.setattr("django.core.mail.message.EmailMessage.send", fail)
            failed = post(signed_in, "/api/assistant/report", report())

        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "base.assistant_report_not_sent"
        assert post(signed_in, "/api/assistant/report", report()).json() == {"sent": True, "duplicate": False}

    def test_reports_are_limited_per_account_as_the_hubs_door(self, signed_in, settings):
        """The Hub's ``report`` door spends ``ASSISTANT_REPORT_RATELIMIT`` per caller; the panel's too, so a signed-in
        account cannot flood the support mailbox with a new ``message_id`` each time."""
        settings.ASSISTANT_REPORT_RATELIMIT = "60/h"
        for number in range(60):
            assert post(signed_in, "/api/assistant/report", report(message_id=f"msg_{number}")).status_code == 200

        refused = post(signed_in, "/api/assistant/report", report(message_id="msg_60"))

        assert (refused.status_code, refused.json()["error"]["code"]) == (429, "rate_limited")
        assert len(mail.outbox) == 60

    def test_the_reports_budget_is_each_accounts_own(self, client, signed_in, make_user, settings):
        settings.ASSISTANT_REPORT_RATELIMIT = "1/h"
        assert post(signed_in, "/api/assistant/report", report()).status_code == 200
        client.force_login(make_user("other@example.com"))

        assert post(client, "/api/assistant/report", report()).status_code == 200

    def test_a_report_without_its_answer_is_a_422(self, signed_in):
        response = post(signed_in, "/api/assistant/report", report(answer=""))

        assert response.status_code == 422
        assert not mail.outbox
