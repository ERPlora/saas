"""WHATSAPP-G06, WHATSAPP-G10 · erplora.com's client of Meta's Graph API.

Meta is replaced at the HTTP border only (``respx``), with bodies of Meta's documentation
(https://developers.facebook.com/docs/graph-api/guides/error-handling). Cases of the old product's
``services/meta.py`` and its tests, plus what it left open (WORKFLOW «Fuentes contrastadas»): the business token
travels in a header, never in the address, and no call follows a redirect.
"""

import logging

import httpx
import pytest
import respx

from whatsapp import meta
from whatsapp.tests.conftest import APP_ID, APP_SECRET, GRAPH

META_ERROR = {
    "error": {
        "message": "(#131047) Re-engagement message",
        "type": "OAuthException",
        "code": 131047,
        "error_subcode": 2494010,
        "error_user_title": "Message failed to send",
        "error_user_msg": "The customer has not written in the last 24 hours.",
        "error_data": {"details": "More than 24 hours have passed since the recipient last replied."},
        "fbtrace_id": "AbCdEf",
    }
}


@respx.mock
def test_a_read_carries_the_token_in_a_header_and_the_version_in_the_address(whatsapp_on):
    route = respx.get(f"{GRAPH}/102290129340398/phone_numbers").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1"}]})
    )

    assert meta.get("102290129340398/phone_numbers", token="EAAG-token") == {"data": [{"id": "1"}]}

    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer EAAG-token"
    assert "EAAG" not in str(request.url)


@respx.mock
def test_a_refusal_carries_metas_code_and_reason(whatsapp_on):
    respx.post(f"{GRAPH}/106540352242922/messages").mock(return_value=httpx.Response(400, json=META_ERROR))

    with pytest.raises(meta.MetaRefused) as refused:
        meta.post("106540352242922/messages", token="EAAG-token", json={"to": "34600111222"})

    error = refused.value
    assert (error.status, error.code, error.subcode) == (400, 131047, 2494010)
    assert error.title == "Message failed to send"
    assert error.user_message == "The customer has not written in the last 24 hours."
    assert error.detail.startswith("More than 24 hours")
    assert error.rate_limited is False


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (429, {"error": {"message": "Too many calls", "code": 4}}),
        (400, {"error": {"message": "(#80007) Rate limit", "code": 80007}}),
        (400, {"error": {"message": "(#130429) Throughput", "code": 130429}}),
    ],
)
@respx.mock
def test_metas_rate_limits_read_as_such(whatsapp_on, status, body):
    respx.get(f"{GRAPH}/x").mock(return_value=httpx.Response(status, json=body))

    with pytest.raises(meta.MetaRefused) as refused:
        meta.get("x", token="t")

    assert refused.value.rate_limited is True


@respx.mock
def test_a_refusal_without_metas_envelope_still_says_its_status(whatsapp_on):
    respx.get(f"{GRAPH}/x").mock(return_value=httpx.Response(403, text="<html>no</html>"))

    with pytest.raises(meta.MetaRefused) as refused:
        meta.get("x", token="t")

    assert (refused.value.status, refused.value.code) == (403, None)


@respx.mock
def test_a_5xx_is_unreachable_and_may_have_arrived(whatsapp_on):
    respx.post(f"{GRAPH}/x").mock(return_value=httpx.Response(503, text="busy"))

    with pytest.raises(meta.MetaUnreachable) as unreachable:
        meta.post("x", token="t", json={})

    assert unreachable.value.sent is True


@respx.mock
def test_no_connection_is_unreachable_and_never_arrived(whatsapp_on):
    respx.post(f"{GRAPH}/x").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(meta.MetaUnreachable) as unreachable:
        meta.post("x", token="t", json={})

    assert unreachable.value.sent is False


@respx.mock
def test_a_read_timeout_is_unreachable_and_may_have_arrived(whatsapp_on):
    respx.post(f"{GRAPH}/x").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(meta.MetaUnreachable) as unreachable:
        meta.post("x", token="t", json={})

    assert unreachable.value.sent is True


@respx.mock
def test_a_redirect_is_never_followed(whatsapp_on):
    respx.get(f"{GRAPH}/x").mock(return_value=httpx.Response(302, headers={"Location": "https://evil.example/"}))
    evil = respx.get("https://evil.example/").mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(meta.MetaUnreachable):
        meta.get("x", token="t")

    assert evil.called is False


@respx.mock
def test_an_answer_that_is_not_json_reads_empty(whatsapp_on):
    respx.post(f"{GRAPH}/x").mock(return_value=httpx.Response(200, text="ok"))

    assert meta.post("x", token="t", json={}) == {}


@respx.mock
def test_the_app_secret_never_reaches_a_log(whatsapp_on, caplog):
    """The exchange carries the app's secret in the address, as Meta documents it: httpx's own request log
    (INFO, with the full address) is silenced in the settings, and ours never names it."""
    respx.get(f"{GRAPH}/oauth/access_token").mock(return_value=httpx.Response(200, json={"access_token": "EAAG-new"}))
    caplog.set_level(logging.DEBUG)

    assert meta.exchange_code("the-code") == {"access_token": "EAAG-new"}

    assert APP_SECRET not in caplog.text and "EAAG-new" not in caplog.text


@respx.mock
def test_the_exchange_uses_the_apps_credentials(whatsapp_on):
    route = respx.get(f"{GRAPH}/oauth/access_token").mock(return_value=httpx.Response(200, json={"access_token": "a"}))

    meta.exchange_code("the-code")

    params = route.calls.last.request.url.params
    assert (params["client_id"], params["client_secret"], params["code"]) == (APP_ID, APP_SECRET, "the-code")


def test_without_metas_app_nothing_is_called(whatsapp_on, settings):
    settings.WHATSAPP_APP_SECRET = ""

    with pytest.raises(meta.NotConfigured):
        meta.exchange_code("the-code")


@pytest.mark.parametrize(
    "url",
    [
        "http://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1",
        "https://evil.example/whatsapp_business/attachments/?mid=1",
        "https://lookaside.fbsbx.com.evil.example/x",
    ],
)
@respx.mock
def test_an_attachment_comes_only_from_meta_over_https(whatsapp_on, url):
    with pytest.raises(meta.MetaUnreachable):
        with meta.download(url, token="t"):
            pass

    assert respx.calls.call_count == 0


@respx.mock
def test_an_attachment_streams_from_meta_with_the_token_in_a_header(whatsapp_on):
    url = "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1"
    route = respx.get(url).mock(
        return_value=httpx.Response(200, content=b"\xff\xd8jpeg", headers={"Content-Type": "image/jpeg"})
    )

    with meta.download(url, token="EAAG-token") as response:
        assert b"".join(response.iter_bytes()) == b"\xff\xd8jpeg"

    assert route.calls.last.request.headers["Authorization"] == "Bearer EAAG-token"
