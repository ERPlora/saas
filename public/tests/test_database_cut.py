"""erplora.com and the panel while the database is cut for a moment (ACCOUNTS-F50; PLAN-DB round 2026-11-04e, point 5).

The whole chain of the project, against the real Postgres: ``pg_terminate_backend`` is the server cutting the connection
right before a statement of the request, ``default_transaction_read_only`` the writer refusing writes. The piece itself,
and what it never repeats, is tested in ``live`` (``tests/test_database_cut.py``); here, that the SaaS is wired to it: the
pool hands out no dead connection, a read waits and answers, past the limit a person reads «come back in a moment» with
503 and ``Retry-After``, and what tries again on its own (the Hub's ``/internal``, Stripe's webhook) gets it at once.
"""

import json
import time
import uuid
from unittest.mock import patch

import psycopg
import pytest
from billing.tests.stripe_double import event, signed
from django.db import DatabaseError, connections
from django.template import TemplateSyntaxError
from django.test import Client
from django.utils import translation
from live.database_cut import DatabaseCut
from live.models import OutboxEvent
from live.operations import registry
from psycopg import sql
from psycopg.conninfo import make_conninfo

from accounts.events import BROWSER_TRUST_REVOKED, PREFERENCES_UPDATED, PROFILE_UPDATED
from accounts.signing import signed_headers
from billing.tests.conftest import stripe_double, stripe_keys  # noqa: F401 - Stripe's signature, with no network
from hubs.tests.conftest import SECRET

pytestmark = pytest.mark.django_db(transaction=True)

HOST = "localhost:8001"
PAGE = "/pricing/"
PANEL_READ = "/api/accounts/preferences"
PREFERENCES_UPDATE = "accounts.preferences.update"
PROFILE_UPDATE = "accounts.profile.update"
UNAVAILABLE = "database_unavailable"
UNKNOWN = "database_outcome_unknown"
LIMIT_SECONDS = 1


def _admin() -> psycopg.Connection:
    """The connection that cuts the others: never read only itself, or it could not undo ``_read_only``."""
    params = connections["default"].settings_dict
    conninfo = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    return psycopg.connect(conninfo, autocommit=True, options="-c default_transaction_read_only=off")


def _terminate(pid: int) -> None:
    with _admin() as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
        deadline = time.monotonic() + 5
        while admin.execute("SELECT 1 FROM pg_stat_activity WHERE pid = %s", (pid,)).fetchone():
            assert time.monotonic() < deadline, "the backend outlived pg_terminate_backend"
            time.sleep(0.01)


def _read_only(on: bool) -> None:
    """New sessions of the test database are read only, as the old writer is during a switchover."""
    name = sql.Identifier(connections["default"].settings_dict["NAME"])
    statement = "ALTER DATABASE {} SET default_transaction_read_only = on" if on else "ALTER DATABASE {} RESET default_transaction_read_only"
    with _admin() as admin:
        admin.execute(sql.SQL(statement).format(name))


class Cut:
    """Cuts the connection right before the next ``times`` statements of this thread (``None``: all of them)."""

    def __init__(self, times: int | None = None) -> None:
        self.times = times
        self.done = 0

    def __call__(self, execute, query, params, many, context):
        if self.times is None or self.done < self.times:
            self.done += 1
            _terminate(context["connection"].connection.info.backend_pid)
        return execute(query, params, many, context)


class Refused:
    """The first statement that writes opens the new sessions again, and is itself refused: this session stays read only,
    as a connection to the old writer does. Keeps the statements Postgres refused."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def __call__(self, execute, query, params, many, context):
        statement = str(query).lstrip().upper()
        if statement.startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in statement:
            _read_only(False)
        try:
            return execute(query, params, many, context)
        except DatabaseError:
            self.statements.append(str(query))
            raise


def _new_sessions_read_only() -> None:
    connections["default"].close()
    connections["default"].close_pool()
    _read_only(True)


@pytest.fixture(autouse=True)
def quick_limit(settings, transactional_db):
    settings.LIVE = {**settings.LIVE, "database_cut": {**settings.LIVE["database_cut"], "wait_seconds": LIMIT_SECONDS}}
    yield
    # Before the flush between tests: no connection this test cut, and no session of the pool still read only.
    _read_only(False)
    connections["default"].close()
    connections["default"].close_pool()


@pytest.fixture
def visitor():
    return Client(raise_request_exception=False, headers={"host": HOST})


@pytest.fixture
def person(visitor, ana):
    visitor.force_login(ana)
    return visitor


def request_in(client, url: str, cut: Cut):
    with connections["default"].execute_wrapper(cut):
        return client.get(url)


# --- The pool ---------------------------------------------------------------------------------------------------------


def test_the_pool_hands_out_no_connection_the_server_cut_while_it_was_idle(person, caplog):
    """Nothing waits, nothing fails: the panel's read does not even notice. Read, unlike a public page, from the database."""
    assert person.get(PANEL_READ).status_code == 200
    connections["default"].close()
    with _admin() as admin:
        pids = admin.execute(
            "SELECT pid FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"
        ).fetchall()
    assert pids, "the pool keeps its connection: there has to be one to cut"
    for (pid,) in pids:
        _terminate(pid)
    caplog.clear()

    response = person.get(PANEL_READ)

    assert response.status_code == 200, response.content
    assert [record.getMessage() for record in caplog.records if record.name == "django.request"] == []


# --- Reads ------------------------------------------------------------------------------------------------------------


def test_a_public_page_waits_and_answers(visitor):
    cut = Cut(1)

    response = request_in(visitor, PAGE, cut)

    assert response.status_code == 200
    assert cut.done == 1


def test_a_read_of_the_panel_waits_and_answers(person, ana):
    cut = Cut(1)

    response = request_in(person, PANEL_READ, cut)

    assert response.status_code == 200, response.content
    assert cut.done == 1
    assert response.json()["theme_mode"]


def test_a_read_of_the_panel_that_stays_cut_says_come_back_as_its_envelope(person):
    response = request_in(person, PANEL_READ, Cut())

    assert response.status_code == 503, response.content
    assert response.json()["error"]["code"] == UNAVAILABLE
    assert int(response["Retry-After"]) > 0
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("language", ["en", "es"])
def test_a_page_that_stays_cut_says_come_back_in_the_language_of_the_visitor(visitor, language):
    """With no database at all: every statement is cut, so a page that needed one would be the 500's fallback."""
    with connections["default"].execute_wrapper(Cut()):
        response = visitor.get(PAGE, headers={"accept-language": language})

    with translation.override(language):
        message = DatabaseCut(repeatable=True).message
    assert response.status_code == 503, response.content
    assert int(response["Retry-After"]) > 0
    assert "503.html" in [template.name for template in response.templates]
    assert message in response.content.decode()


def test_a_signed_in_person_on_the_panel_gets_the_page_too(person, spa_manifest):
    """The session and the account are the first reads: they are cut before any view runs."""
    response = request_in(person, "/launch", Cut())

    assert response.status_code == 503, response.content
    assert int(response["Retry-After"]) > 0
    assert "503.html" in [template.name for template in response.templates]


def test_the_page_says_come_back_even_if_it_cannot_be_painted(visitor):
    with connections["default"].execute_wrapper(Cut()), patch(
        "public.errors.render_to_string", side_effect=TemplateSyntaxError("broken")
    ):
        response = visitor.get(PAGE)

    assert response.status_code == 503
    assert int(response["Retry-After"]) > 0
    assert DatabaseCut(repeatable=True).message in response.content.decode()


# --- Writes -----------------------------------------------------------------------------------------------------------


def test_a_save_cut_while_reading_who_asks_is_applied_once(person, ana):
    """The session is read inside the route, the first statement of a save: nothing of it has started."""
    cut = Cut(1)

    with connections["default"].execute_wrapper(cut):
        response = person.post(PANEL_READ, json.dumps({"theme_mode": "dark"}), content_type="application/json")

    assert response.status_code == 200, response.content
    assert cut.done == 1
    assert OutboxEvent.objects.filter(name=PREFERENCES_UPDATED).count() == 1


def test_a_save_refused_as_read_only_is_applied_once(person, ana):
    """The session the pool had stays read only: the try after it needs a new one."""
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = person.post(PANEL_READ, json.dumps({"theme_mode": "dark"}), content_type="application/json")

    assert response.status_code == 200, response.content
    assert response.json()["theme_mode"] == "dark"
    # At least the one of the first try; the pool may hold more sessions from before, each one a try of its own.
    assert refused.statements
    assert OutboxEvent.objects.filter(name=PREFERENCES_UPDATED).count() == 1


def test_a_change_of_name_refused_as_read_only_is_applied_once(person, ana):
    _new_sessions_read_only()

    with connections["default"].execute_wrapper(Refused()):
        response = person.post(
            "/api/accounts/profile", json.dumps({"first_name": "Lena", "last_name": "Ruiz"}), content_type="application/json"
        )

    assert response.status_code == 200, response.content
    assert response.json()["first_name"] == "Lena"
    assert OutboxEvent.objects.filter(name=PROFILE_UPDATED).count() == 1


def test_only_what_touches_nothing_but_its_database_says_it_can_repeat():
    """A command joins this list after reading its body and what it calls: a charge, a numbering, a call to a third party
    or a mail sent in it would run twice. Nothing of billing, fiscal or the assistant's providers, ever."""
    declared = {op.name for op in registry.values() if op.repeatable}

    assert declared == {PREFERENCES_UPDATE, PROFILE_UPDATE}


def test_a_write_that_does_not_say_it_can_repeat_is_not_repeated(person, ana):
    """Only what declares it runs twice: its 503 asks the person to check first."""
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = person.post("/api/accounts/browser-trust/revoke", json.dumps({}), content_type="application/json")

    assert response.status_code == 503, response.content
    assert response.json()["error"]["code"] == UNKNOWN
    assert int(response["Retry-After"]) > 0
    assert sum("mfa_authenticator" in statement for statement in refused.statements) == 1
    assert OutboxEvent.objects.filter(name=BROWSER_TRUST_REVOKED).count() == 0


# --- What tries again on its own --------------------------------------------------------------------------------------


def test_the_hubs_internal_call_gets_its_503_at_once(visitor, settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    hub_id = uuid.uuid7()
    path = f"/internal/hubs/{hub_id}/ready"
    body = json.dumps({"id": str(hub_id)}).encode()
    headers = {**signed_headers("POST", path, body, int(time.time()), SECRET), "host": HOST}
    cut = Cut()

    with connections["default"].execute_wrapper(cut):
        response = visitor.post(path, body, content_type="application/json", headers=headers)

    assert response.status_code == 503, response.content
    assert cut.done == 1


def test_stripes_webhook_gets_its_503_at_once(visitor, stripe_double):
    body, header = signed(event("product.created", {"id": "prod_1", "object": "product"}, event_id="evt_cut"))
    cut = Cut()

    with connections["default"].execute_wrapper(cut):
        response = visitor.post("/webhooks/stripe/", body, content_type="application/json", headers={"stripe-signature": header})

    assert response.status_code == 503, response.content
    assert int(response["Retry-After"]) > 0
    assert cut.done == 1
