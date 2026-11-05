"""erplora.com and the panel while the database is cut for a moment (ACCOUNTS-F50; PLAN-DB round 2026-11-04e, point 5).

The whole chain of the project, against the real Postgres: ``pg_terminate_backend`` is the server cutting the connection
right before a statement of the request, ``default_transaction_read_only`` the writer refusing writes. The piece itself,
and what it never repeats, is tested in ``live`` (``tests/test_database_cut.py``); here, that the SaaS is wired to it: the
pool hands out no dead connection, a read waits and answers, past the limit a person reads «come back in a moment» with
503 and ``Retry-After``, and what tries again on its own (the Hub's ``/internal``, Stripe's webhook) gets it at once.
"""

import base64
import hashlib
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import django_ratelimit.core
import psycopg
import pytest
from allauth.account.models import EmailAddress
from billing.tests.stripe_double import event, signed
from django.core import mail
from django.db import DatabaseError, connections
from django.template import TemplateSyntaxError
from django.test import Client
from django.utils import timezone, translation
from live.database_cut import DatabaseCut
from live.models import OutboxEvent
from live.operations import registry
from psycopg import sql
from psycopg.conninfo import make_conninfo

from accounts import photos, services
from accounts.events import BROWSER_TRUST_REVOKED, PREFERENCES_UPDATED, PROFILE_UPDATED
from accounts.models import EmailChangeRequest, ProfilePhoto, UserPreferences
from accounts.signing import signed_headers
from accounts.tests.images import png
from billing.tests.conftest import stripe_double, stripe_keys  # noqa: F401 - Stripe's signature, with no network
from hubs.events import BUSINESS_CREATED
from hubs.models import Hub
from hubs.tests.conftest import SECRET, offline_hub, plans  # noqa: F401 - the plans a new business takes, no Hub

pytestmark = pytest.mark.django_db(transaction=True)

HOST = "localhost:8001"
PAGE = "/pricing/"
PANEL_READ = "/api/accounts/preferences"
PREFERENCES_UPDATE = "accounts.preferences.update"
PROFILE_UPDATE = "accounts.profile.update"
UNAVAILABLE = "database_unavailable"
UNKNOWN = "database_outcome_unknown"
APPLIED = "database_answer_lost"
NEW_EMAIL = "ana.garcia@new.example"
#: The commands a cut before their COMMIT runs again: their body and what it calls touch nothing but the database
#: (what leaves, a mail or the push to the Hub, leaves in ``on_commit``), or count their try once per request (the
#: photo and the email's code). Each one was read before joining.
REPEATABLE = {
    "accounts.apikey.create",
    "accounts.apikey.revoke",
    "accounts.browser_trust.revoke",
    "accounts.email.verify",
    "accounts.photo.remove",
    "accounts.photo.upload",
    PREFERENCES_UPDATE,
    PROFILE_UPDATE,
    "accounts.session.close_others",
    "hubs.business.change_address",
    "hubs.business.create",
    "hubs.business.delete",
    "hubs.business.open",
    "hubs.business.restore",
    "hubs.business.update",
    "hubs.invitation.accept",
    "hubs.invitation.decline",
    "hubs.member.cancel",
    "hubs.member.change_role",
    "hubs.member.invite",
    "hubs.member.remove",
    "hubs.member.resend",
    "hubs.ownership.cancel",
    "hubs.ownership.decline",
    "hubs.ownership.transfer",
}
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


class CutOn:
    """Cuts the connection right before the first statement that names ``table``, once."""

    def __init__(self, table: str) -> None:
        self.table = table
        self.done = 0

    def __call__(self, execute, query, params, many, context):
        if not self.done and self.table in str(query):
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


def test_a_change_of_language_cut_at_its_last_statement_is_saved(person, ana):
    """The try the cut rolled back left the account's new language in memory, not in the database: the try after it
    still saves it."""
    cut = CutOn("live_outboxevent")

    with connections["default"].execute_wrapper(cut):
        response = person.post(PANEL_READ, json.dumps({"language": "en"}), content_type="application/json")

    assert response.status_code == 200, response.content
    assert cut.done == 1
    ana.refresh_from_db()
    assert ana.language == "en"
    assert OutboxEvent.objects.filter(name=PREFERENCES_UPDATED).count() == 1


def test_only_what_touches_nothing_but_its_database_says_it_can_repeat():
    """A command joins this list after reading its body and what it calls: a charge, a numbering, a call to a third party,
    a mail, a counter in the cache or a change of the session sent in it would run twice. Nothing of billing, fiscal or
    the assistant's providers, ever."""
    declared = {op.name for op in registry.values() if op.repeatable}

    assert declared == REPEATABLE


def test_stopping_the_trust_of_every_browser_refused_as_read_only_is_applied_once(person, ana):
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = person.post("/api/accounts/browser-trust/revoke", json.dumps({}), content_type="application/json")

    assert response.status_code == 200, response.content
    assert refused.statements
    assert OutboxEvent.objects.filter(name=BROWSER_TRUST_REVOKED).count() == 1


def test_a_cut_after_the_trust_was_stopped_leaves_this_browser_the_code_it_gave(person, ana):
    """The session follows the authenticators' new ids once nothing else is left to write: the try the cut rolled back
    never touched it, so the one after it renames from the ids the database kept."""
    from allauth.account.internal.flows.login import AUTHENTICATION_METHODS_SESSION_KEY
    from allauth.mfa.models import Authenticator

    app = Authenticator.objects.create(user=ana, type=Authenticator.Type.TOTP, data={"secret": "JBSWY3DPEHPK3PXP"})
    session = person.session
    session[AUTHENTICATION_METHODS_SESSION_KEY] = [{"method": "mfa", "type": "totp", "id": app.pk, "at": time.time()}]
    session.save()
    cut = CutOn("live_outboxevent")

    with connections["default"].execute_wrapper(cut):
        response = person.post("/api/accounts/browser-trust/revoke", json.dumps({}), content_type="application/json")

    assert response.status_code == 200, response.content
    assert cut.done == 1
    renamed = Authenticator.objects.get(user=ana).pk
    assert renamed != app.pk
    assert [record["id"] for record in person.session[AUTHENTICATION_METHODS_SESSION_KEY]] == [renamed]


def test_a_new_business_refused_as_read_only_is_created_once(person, ana, plans, offline_hub):  # noqa: F811
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = person.post(
            "/api/hubs/businesses", json.dumps({"name": "Bar Manolo", "country": "ES"}), content_type="application/json"
        )

    assert response.status_code == 201, response.content
    assert refused.statements
    assert Hub.objects.filter(name="Bar Manolo").count() == 1
    assert OutboxEvent.objects.filter(name=BUSINESS_CREATED).count() == 1


def test_a_write_that_does_not_say_it_can_repeat_is_not_repeated(person, ana):
    """Only what declares it runs twice: its 503 asks the person to check first. A code to the email is mailed in its
    body, which no rollback unsends."""
    EmailAddress.objects.create(user=ana, email=ana.email, verified=False, primary=True)
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = person.post(
            "/api/accounts/email/change", json.dumps({"email": ana.email}), content_type="application/json"
        )

    assert response.status_code == 503, response.content
    assert response.json()["error"]["code"] == UNKNOWN
    assert int(response["Retry-After"]) > 0
    assert sum("accounts_emailchangerequest" in statement for statement in refused.statements) == 1
    assert not EmailChangeRequest.objects.exists()
    assert mail.outbox == []


def _upload(client):
    image = base64.b64encode(png()).decode()
    return client.post("/api/accounts/photo", json.dumps({"image": image}), content_type="application/json")


def _photo_usage(ana, *, increment: bool = False) -> dict:
    """The account's uploads this hour, as ``accounts.photo.upload`` counts them; ``increment``, another tab's."""
    rate = f"{photos.UPLOADS_PER_HOUR}/h"
    key = f"user:{ana.pk}"
    return django_ratelimit.core.get_usage(
        None, group="accounts.photo.upload", key=lambda group, request: key, rate=rate, increment=increment
    )


def _photo_uploads(ana, *, increment: bool = False) -> int:
    return _photo_usage(ana, increment=increment)["count"]


def test_a_photo_refused_as_read_only_is_kept_once_and_counts_one_upload(person, ana, monkeypatch):
    """The upload the cut rolled back runs again and counts once: the person still has the other upload of the hour."""
    monkeypatch.setattr(photos, "UPLOADS_PER_HOUR", 2)
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = _upload(person)

    assert response.status_code == 200, response.content
    assert response.json()["photo"].startswith("data:image/png;base64,")
    assert refused.statements
    assert ProfilePhoto.objects.filter(user=ana).count() == 1
    assert OutboxEvent.objects.filter(name=PROFILE_UPDATED).count() == 1
    assert _upload(person).status_code == 200
    assert _upload(person).json()["error"]["code"] == "accounts.too_many_attempts"


def test_an_upload_whose_hour_turned_while_the_database_was_cut_counts_in_the_new_one(person, ana, monkeypatch):
    """The count the rolled back try left is the hour that ended: the try after it counts in the new one, so a cut
    never hands out an upload."""
    clock = [time.time()]
    monkeypatch.setattr(django_ratelimit.core, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(photos, "UPLOADS_PER_HOUR", 1)
    _new_sessions_read_only()
    refused = Refused()

    def as_the_hour_turns(execute, query, params, many, context):
        try:
            return refused(execute, query, params, many, context)
        except DatabaseError:
            if len(refused.statements) == 1:
                clock[0] += _photo_usage(ana)["time_left"] + 1  # the second after the hour ends, during the cut
            raise

    with connections["default"].execute_wrapper(as_the_hour_turns):
        response = _upload(person)

    assert response.status_code == 200, response.content
    assert refused.statements
    assert _upload(person).json()["error"]["code"] == "accounts.too_many_attempts"


def test_an_upload_the_cut_rolled_back_keeps_its_place_under_the_limit(person, ana, monkeypatch):
    """It was counted within the limit before the cut: another tab's upload counted meanwhile is the one past it."""
    monkeypatch.setattr(photos, "UPLOADS_PER_HOUR", 1)
    _new_sessions_read_only()
    refused = Refused()
    meanwhile = []

    def while_cut(execute, query, params, many, context):
        try:
            return refused(execute, query, params, many, context)
        except DatabaseError:
            if not meanwhile:
                meanwhile.append(_photo_uploads(ana, increment=True))
            raise

    with connections["default"].execute_wrapper(while_cut):
        response = _upload(person)

    assert response.status_code == 200, response.content
    assert meanwhile == [2]
    assert _photo_uploads(ana) == 2
    assert ProfilePhoto.objects.filter(user=ana).count() == 1


def _waiting_code(person, ana, code: str = "123456") -> None:
    """A change of email waiting for ``code`` in the person's session, as ``accounts.email.change`` leaves it."""
    EmailChangeRequest.objects.create(
        user=ana,
        session_key=person.session.session_key,
        email=NEW_EMAIL,
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        created_at=timezone.now(),
    )


def _verify(client, code: str):
    return client.post("/api/accounts/email/verify", json.dumps({"code": code}), content_type="application/json")


def test_a_wrong_code_refused_as_read_only_is_one_try(person, ana, monkeypatch):
    """One try of the code and of the account's budget, not two: the budget still stops the try past it."""
    monkeypatch.setattr(services, "EMAIL_CODE_TRIES_PER_MINUTE", "2/m")
    _waiting_code(person, ana)
    _new_sessions_read_only()
    refused = Refused()

    with connections["default"].execute_wrapper(refused):
        response = _verify(person, "000000")

    assert response.status_code == 200, response.content
    assert (response.json()["verified"], response.json()["attempts_left"]) == (False, 2)
    assert refused.statements
    assert _verify(person, "000001").json()["attempts_left"] == 1
    refused_past_the_budget = _verify(person, "123456")
    assert (refused_past_the_budget.status_code, refused_past_the_budget.json()["error"]["code"]) == (
        429,
        "accounts.too_many_attempts",
    )


def test_the_right_code_cut_at_its_last_statement_changes_the_email_once(person, ana):
    """The whole change ran, the old address's mail waiting for the COMMIT, when the cut rolled it back: the try after it
    changes the email, records it and mails the old address once."""
    _waiting_code(person, ana)
    cut = CutOn("live_outboxevent")

    with connections["default"].execute_wrapper(cut):
        response = _verify(person, "123456")

    assert response.status_code == 200, response.content
    assert response.json()["verified"] is True
    assert cut.done == 1
    ana.refresh_from_db()
    assert ana.email == NEW_EMAIL
    assert not EmailChangeRequest.objects.exists()
    assert OutboxEvent.objects.filter(name=PROFILE_UPDATED).count() == 1
    assert [message.to for message in mail.outbox] == [["ana@example.com"]]


def test_a_save_whose_answer_the_cut_lost_says_it_was_saved(person, ana):
    """The preferences committed; the record of the session's use, after the view, is what the cut stopped. It was saved,
    so the person is not asked to check: only to reload."""
    cut = CutOn("usersessions_usersession")

    with connections["default"].execute_wrapper(cut):
        response = person.post(PANEL_READ, json.dumps({"theme_mode": "dark"}), content_type="application/json")

    assert response.status_code == 503, response.content
    assert response.json()["error"]["code"] == APPLIED
    assert response.json()["error"]["message"] == DatabaseCut(repeatable=False, applied=True).message
    assert int(response["Retry-After"]) > 0
    assert cut.done == 1
    assert UserPreferences.objects.get(user=ana).theme_mode == "dark"
    assert OutboxEvent.objects.filter(name=PREFERENCES_UPDATED).count() == 1


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
