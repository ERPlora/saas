"""ASSISTANT-F21 · The dictation of erplora.com's own panel: ``POST /api/assistant/transcribe``
(``base.assistant.transcribe``, the Hub's same name and path, saas#175), for the signed-in account.

The gateway is called in process, with no ``/internal`` and no signature: the same audio limit, the same provider, the
budget of dictations per hour per account, and the dictation is counted in the account's month without spending a
message. A connection never waits on the provider inside a transaction, so the operation is the door (the session, the
permission, the budget) and the wait goes after it, in the route, as the turn's. The provider is the local fake.
"""

import base64
import io
import json
import logging

import pytest
from django.core.management import call_command
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from live.ninja import ensure_api_parity, operation_ids
from live.operations import current_operation

from assistant import media
from assistant import turn as gateway
from assistant.internal import TRANSCRIBE_BODY_BYTES
from assistant.models import AssistantUsage
from assistant.schemas import Caller
from assistant.tests.conftest import (  # noqa: F401 - the gateway's fixtures
    API_KEY,
    answering,
    fake_provider,
    fernet_key,
    provider,
)
from config.api import api
from config.asgi import body_ceiling
from config.tests.asgi_bodies import asgi_post, files_written
from hubs.tests.conftest import make_user, plans  # noqa: F401 - shared fixtures

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
ROUTE = "/api/assistant/transcribe"
PROVIDER = "/v1/audio/transcriptions"
AUDIO = b"\x1aE\xdf\xa3 a few seconds of webm"
SECRET_WORDS = "Rosalía Quintanar debe 400 euros"


def clip(audio: bytes = AUDIO, **change) -> dict:
    return {"audio": base64.b64encode(audio).decode(), "mime_type": "audio/webm", "language": "es", **change}


def post(client, data: dict):
    return client.post(ROUTE, json.dumps(data), content_type="application/json", HTTP_HOST=HOST)


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def month_of(account) -> tuple[int, int]:
    """What the account's month counts: its messages and its dictations (nothing yet, nothing was counted)."""
    row = AssistantUsage.objects.filter(user=account).first()
    return (row.messages, row.transcriptions) if row else (0, 0)


@pytest.fixture
def account(make_user):
    return make_user("lena@example.com", first_name="Lena", language="en")


@pytest.fixture
def signed_in(client, account):
    client.force_login(account)
    return client


class TestTheRoute:
    def test_it_is_bound_to_its_operation_and_listed_in_the_openapi(self, client):
        assert ensure_api_parity(api) == []
        assert "base.assistant.transcribe" in operation_ids(api)
        paths = client.get("/api/openapi.json", HTTP_HOST=HOST).json()["paths"]
        assert paths[ROUTE]["post"]["operationId"] == "base.assistant.transcribe"

    def test_without_a_session_it_is_a_401_and_the_provider_hears_nothing(self, client, answering, fake_provider):
        assert error(post(client, clip())) == (401, "unauthorized")
        assert fake_provider.requests == []

    def test_without_the_assistants_permission_it_is_a_403(self, signed_in, answering, fake_provider, monkeypatch):
        from live.meta import all_live_app_configs, permissions_for_role

        from base import operations

        granted = permissions_for_role(all_live_app_configs(), operations.ACCOUNT_ROLE) - {"assistant.ask"}
        monkeypatch.setattr(operations, "_permissions", lambda actor: granted)

        assert error(post(signed_in, clip())) == (403, "permission_denied")
        assert fake_provider.requests == []

    def test_its_body_stays_in_memory_up_to_the_dictations_ceiling(self):
        assert body_ceiling({"path": ROUTE, "headers": []}) == TRANSCRIBE_BODY_BYTES
        over = str(TRANSCRIBE_BODY_BYTES + 1).encode()
        assert body_ceiling({"path": ROUTE, "headers": [(b"content-length", over)]}) == 0


class TestTheBodyInMemory:
    @pytest.fixture(autouse=True)
    def keep_the_test_connection(self):
        """Django's real handler closes old connections around a request, which would drop the test's transaction."""
        request_started.disconnect(close_old_connections)
        request_finished.disconnect(close_old_connections)
        yield
        request_started.connect(close_old_connections)
        request_finished.connect(close_old_connections)

    def test_a_large_dictation_never_touches_the_disk(self):
        """Past Django's 2.5 MB its handler opens a file, before any view; this body stays in memory, whatever the
        request then gets (here, without a session or a CSRF cookie, a 403). The control, that any other path does open
        one: ``assistant/tests/test_body_in_memory.py``."""
        body = json.dumps(clip(b"0" * media.MAX_AUDIO_BYTES)).encode()
        assert len(body) > 2_500_000

        with files_written() as written:
            status, _, _ = asgi_post(ROUTE, body, secret="", chunks=3)

        assert status == 403
        assert written == []

    def test_a_body_over_the_ceiling_is_dropped_and_refused(self):
        with files_written() as written:
            status, answer, unread = asgi_post(ROUTE, b"x" * (TRANSCRIBE_BODY_BYTES + 5), secret="", chunks=4)

        assert (status, answer["error"]["code"]) == (413, "payload_too_large")
        assert written == [] and unread == 0


class TestTheDictation:
    def test_the_audio_comes_back_as_text_in_the_language_asked(self, signed_in, answering, fake_provider):
        fake_provider.reply("POST", PROVIDER, json={"text": "  Dos cafés y una tostada  "})

        response = post(signed_in, clip(mime_type="audio/webm;codecs=opus", language="es-ES"))

        assert response.status_code == 200
        assert response.json() == {"text": "Dos cafés y una tostada", "language": "es"}
        [asked] = fake_provider.requests
        assert asked.headers["authorization"] == f"Bearer {API_KEY}"
        assert 'filename="dictation.webm"' in asked.body
        assert 'name="language"' in asked.body

    @pytest.mark.parametrize("language", ["es", "en"])
    def test_without_a_language_it_is_the_one_of_the_account(self, client, make_user, answering, fake_provider, language):
        client.force_login(make_user(f"{language}@example.com", language=language))
        fake_provider.reply("POST", PROVIDER, json={"text": "Hola"})

        response = post(client, clip(language=""))

        assert response.json() == {"text": "Hola", "language": language}
        assert 'name="language"' in fake_provider.requests[0].body

    def test_it_counts_a_dictation_in_the_accounts_month_and_spends_no_message(
        self, signed_in, account, answering, fake_provider
    ):
        fake_provider.reply("POST", PROVIDER, json={"text": "Hola"})

        post(signed_in, clip())

        assert month_of(account) == (0, 1)

    def test_two_megabytes_of_audio_pass(self, signed_in, answering, fake_provider):
        """In base64, 2.8 MB: over Django's 2.5 MB of a request's body, which would refuse it without its route's own."""
        fake_provider.reply("POST", PROVIDER, json={"text": "Hola"})

        assert post(signed_in, clip(b"0" * media.MAX_AUDIO_BYTES)).status_code == 200

    def test_more_than_two_megabytes_of_audio_is_a_413(self, signed_in, account, answering, fake_provider):
        response = post(signed_in, clip(b"0" * (media.MAX_AUDIO_BYTES + 1)))

        assert error(response) == (413, "base.assistant_audio_too_long")
        assert fake_provider.requests == []
        assert month_of(account) == (0, 0)

    def test_a_body_over_the_ceiling_is_a_413(self, signed_in, answering, fake_provider):
        response = post(signed_in, {**clip(), "audio": "A" * (TRANSCRIBE_BODY_BYTES + 1)})

        assert error(response) == (413, "payload_too_large")
        assert fake_provider.requests == []

    @pytest.mark.parametrize(
        ("change", "field"),
        [({"audio": "@@not base64@@"}, "audio"), ({"audio": ""}, "audio"), ({"mime_type": "video/mp4"}, "mime_type")],
    )
    def test_what_is_not_audio_is_a_422_naming_its_field(self, signed_in, answering, fake_provider, change, field):
        response = post(signed_in, {**clip(), **change})

        assert error(response) == (422, "invalid_payload")
        assert field in response.json()["error"]["fields"]
        assert fake_provider.requests == []

    def test_an_audio_of_nothing_is_a_422(self, signed_in, answering, fake_provider):
        """Valid base64 of no bytes at all: the gateway's own ``empty``."""
        response = post(signed_in, {**clip(), "audio": "===="})

        assert error(response) == (422, "invalid_payload")
        assert "audio" in response.json()["error"]["fields"]
        assert fake_provider.requests == []

    def test_without_the_services_provider_it_is_a_503_and_counts_nothing(
        self, signed_in, account, answering, fake_provider, settings
    ):
        settings.ASSISTANT_SERVICE_PROVIDER = "nobody"

        assert error(post(signed_in, clip())) == (503, "assistant.provider_not_configured")
        assert fake_provider.requests == []
        assert month_of(account) == (0, 0)

    @pytest.mark.parametrize("status", [401, 500])
    def test_a_failure_of_the_provider_is_a_503_that_counts_nothing_and_hides_the_key(
        self, signed_in, account, answering, fake_provider, status
    ):
        fake_provider.reply("POST", PROVIDER, status=status, json={"error": {"message": f"key {API_KEY}"}})

        response = post(signed_in, clip())

        assert error(response) == (503, "base.assistant_transcribe_failed")
        assert API_KEY not in response.content.decode()
        assert month_of(account) == (0, 0)

    def test_what_it_refuses_speaks_the_language_of_the_account(self, client, make_user, answering, fake_provider):
        client.force_login(make_user("es@example.com", language="es"))
        fake_provider.reply("POST", PROVIDER, status=500, json={"error": {"message": "busy"}})
        failed = post(client, clip())
        too_long = post(client, clip(b"0" * (media.MAX_AUDIO_BYTES + 1)))

        assert error(failed) == (503, "base.assistant_transcribe_failed")
        assert failed.json()["error"]["message"] != "The audio could not be transcribed: try again."
        assert error(too_long) == (413, "base.assistant_audio_too_long")
        assert too_long.json()["error"]["message"] != "The recording is too long: dictate a shorter message."


class TestTheBudget:
    def test_past_its_budget_an_account_waits_and_another_one_does_not(
        self, signed_in, make_user, answering, fake_provider, settings
    ):
        settings.ASSISTANT_TRANSCRIBE_RATELIMIT = "1/h"
        fake_provider.reply("POST", PROVIDER, always=True, json={"text": "Hola"})

        assert post(signed_in, clip()).status_code == 200
        assert error(post(signed_in, clip())) == (429, "rate_limited")
        assert len(fake_provider.requests) == 1

        signed_in.force_login(make_user("otra@example.com", language="en"))
        assert post(signed_in, clip()).status_code == 200


    def test_it_spends_the_budget_of_the_dictations_and_no_other_door(
        self, signed_in, account, answering, fake_provider, settings
    ):
        """The Hub's ``transcribe`` door's, per account: a dictation never eats what a report or a reading aloud may spend."""
        settings.ASSISTANT_TRANSCRIBE_RATELIMIT = "1/h"
        fake_provider.reply("POST", PROVIDER, json={"text": "Hola"})

        assert post(signed_in, clip()).status_code == 200

        with pytest.raises(gateway.Refused):
            gateway.spend(None, "transcribe", "1/h", Caller(user_id=account.pk))


class TestWhileItWaits:
    def test_no_transaction_is_open_while_the_provider_answers(self, signed_in, answering, monkeypatch):
        seen = []

        async def spying(service, audio, mime_type, language):
            seen.append(current_operation.get())
            return "Hola"

        monkeypatch.setattr(media, "transcribe", spying)

        assert post(signed_in, clip()).status_code == 200
        assert seen == [None]


class TestItForgets:
    def test_what_is_dictated_is_kept_in_no_table_and_no_log(self, signed_in, answering, fake_provider, caplog):
        """ASSISTANT-F17: the account's dictation is forgotten as the Hub's is, whichever way it ends."""
        caplog.set_level(logging.DEBUG)
        fake_provider.reply("POST", PROVIDER, json={"text": SECRET_WORDS})
        fake_provider.reply("POST", PROVIDER, status=500, json={"error": {"message": SECRET_WORDS}})

        assert post(signed_in, clip()).json()["text"] == SECRET_WORDS
        assert post(signed_in, clip()).status_code == 503

        kept = io.StringIO()
        call_command("dumpdata", stdout=kept)
        assert SECRET_WORDS not in kept.getvalue()
        assert SECRET_WORDS not in "\n".join(record.getMessage() for record in caplog.records)
