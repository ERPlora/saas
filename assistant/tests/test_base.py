"""The common part of the providers' clients (``assistant.providers.base``, ASSISTANT-G33): the events every client
yields, the reading of a server-sent stream, which upstream failures another attempt can clear, and the helpers
that shape a conversation for each API."""

import json
import logging
import socket

import httpx
import pytest

from assistant.providers.base import (
    Provider,
    ProviderError,
    ProviderEvent,
    TurnRequest,
    is_retriable_status,
    redact,
    sse_events,
)
from assistant.providers.openai import OpenAIProvider


class _Lines(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


async def events_of(*chunks: bytes) -> list[tuple[str | None, str]]:
    response = httpx.Response(200, stream=_Lines(list(chunks)))
    return [event async for event in sse_events(response)]


@pytest.mark.asyncio
async def test_a_stream_is_read_event_by_event_even_split_across_chunks():
    found = await events_of(
        b'data: {"a": 1}\n\n',
        b'event: message_delta\ndata: {"b"',
        b": 2}\n\n: a comment line\n\ndata: [DONE]\n\n",
    )

    assert found == [(None, '{"a": 1}'), ("message_delta", '{"b": 2}'), (None, "[DONE]")]


@pytest.mark.asyncio
async def test_an_event_with_several_data_lines_joins_them_and_crlf_is_accepted():
    found = await events_of(b"data: first\r\ndata: second\r\n\r\n", b"data: last")

    assert found == [(None, "first\nsecond"), (None, "last")]


@pytest.mark.parametrize(
    ("status", "retriable"),
    [(None, True), (408, True), (409, True), (425, True), (429, True), (500, True), (503, True), (400, False), (401, False), (403, False), (404, False), (422, False)],
)
def test_only_timeouts_conflicts_rate_limits_and_server_errors_are_retriable(status, retriable):
    assert is_retriable_status(status) is retriable


def test_the_key_is_never_repeated_in_a_message():
    assert redact("Incorrect API key provided: sk-abc123", "sk-abc123") == "Incorrect API key provided: …"
    assert redact("nothing to hide", "") == "nothing to hide"


def test_an_event_is_its_type_and_payload():
    event = ProviderEvent("text_delta", {"text": "Hi"})

    assert (event.type, event.payload) == ("text_delta", {"text": "Hi"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, "{}"), ("", "{}"), ('{"a": 1}', '{"a": 1}'), ("not json", json.dumps({"_raw": "not json"})), ({"a": 1}, '{"a": 1}')],
)
def test_tool_arguments_always_become_a_json_string(raw, expected):
    assert Provider.normalize_tool_arguments(raw) == expected


def test_consecutive_messages_of_one_role_merge_into_one():
    merged = Provider.merge_consecutive_same_role(
        [
            {"role": "user", "content": "a"},
            {"role": "user", "content": [{"type": "text", "text": "b"}]},
            {"role": "assistant", "content": "c"},
        ]
    )

    assert merged == [
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
        {"role": "assistant", "content": "c"},
    ]


def test_system_messages_are_split_from_the_rest():
    system, rest = Provider.split_system_messages(
        [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hi"},
            {"role": "system", "content": "  "},
            {"role": "system", "content": "Speak Spanish."},
        ]
    )

    assert system == "Be brief.\n\nSpeak Spanish."
    assert rest == [{"role": "user", "content": "Hi"}]


def test_a_client_without_a_key_is_unavailable():
    from assistant.providers.base import ProviderUnavailable
    from assistant.providers.openai import OpenAIProvider

    with pytest.raises(ProviderUnavailable):
        OpenAIProvider(api_key="", base_url="https://api.openai.com/v1")


# --- The server's trusted certificates (FIX-SAAS-ASSISTANT-GATEWAY-502-WHEN-SSL-CERT-FILE-MISSING) ------------------

KEY = "sk-test-base-0000"


def nowhere() -> OpenAIProvider:
    """A client of a provider on a free port of ``127.0.0.1``, over ``http://``: the real ``httpx``, nothing patched."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return OpenAIProvider(api_key=KEY, base_url=f"http://127.0.0.1:{port}/v1")


@pytest.fixture(params=["missing", "not_a_certificate"])
def unreadable_ca(request, missing_ca):
    """``SSL_CERT_FILE`` naming a file that is not there, or one that holds no certificate."""
    if request.param == "not_a_certificate":
        missing_ca.write_text("not a certificate\n")
    return missing_ca


def names_the_file(message: str, path) -> bool:
    return "SSL_CERT_FILE" in message and str(path) in message


@pytest.mark.asyncio
async def test_a_turn_without_the_servers_certificates_ends_in_a_final_error_naming_the_file(unreadable_ca, caplog):
    request = TurnRequest(model_id="gpt-test", messages=[{"role": "user", "content": "Hi"}])

    with caplog.at_level(logging.ERROR, logger="assistant"):
        events = [event async for event in nowhere().stream_turn(request)]

    assert [event.type for event in events] == ["error", "finish"]
    assert events[1].payload == {"reason": "error"}
    assert events[0].payload["retriable"] is False
    assert events[0].payload["message"].startswith("openai: ")
    assert names_the_file(events[0].payload["message"], unreadable_ca)
    assert any(names_the_file(record.getMessage(), unreadable_ca) for record in caplog.records)


@pytest.mark.asyncio
async def test_a_listing_without_the_servers_certificates_is_a_final_error_naming_the_file(unreadable_ca):
    provider = nowhere()

    with pytest.raises(ProviderError) as raised:
        await provider.get_json(f"{provider.base_url}/models", {})

    assert raised.value.retriable is False
    assert raised.value.message.startswith("openai: ")
    assert names_the_file(raised.value.message, unreadable_ca)


@pytest.mark.asyncio
async def test_the_failure_of_the_servers_certificates_never_carries_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / f"{KEY}.pem"))
    request = TurnRequest(model_id="gpt-test", messages=[{"role": "user", "content": "Hi"}])

    provider = nowhere()

    events = [event async for event in provider.stream_turn(request)]
    with pytest.raises(ProviderError) as raised:
        await provider.get_json(f"{provider.base_url}/models", {})

    assert "SSL_CERT_FILE" in events[0].payload["message"] and KEY not in events[0].payload["message"]
    assert "SSL_CERT_FILE" in raised.value.message and KEY not in raised.value.message


@pytest.mark.asyncio
async def test_without_ssl_cert_file_the_failure_of_the_bundled_certificates_is_final_too(tmp_path, monkeypatch):
    import certifi

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(certifi, "where", lambda: str(tmp_path / "gone.pem"))
    provider = nowhere()

    with pytest.raises(ProviderError) as raised:
        await provider.get_json(f"{provider.base_url}/models", {})

    assert raised.value.retriable is False
    assert "SSL_CERT_FILE" not in raised.value.message
