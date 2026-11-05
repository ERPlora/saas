"""The per-response tokens in the tests of the public web (saas#261, saas#264).

Every public page carries a CSRF token and a CSP nonce, drawn at random for each response. A test
that scans the raw page for a word depends on that draw not holding the word: «SdI» in a token
stopped a deploy of main. So ``fixed_response_tokens`` (conftest.py) gives every test here one value
that means nothing. This file says that it does what it promises, and that it hides nothing: it
fixes the value of the tokens, it does not provide them.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.django_db

PATH = "/compliance/"
WORD = "SdI"
CSRF_INPUT = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
HEADER_NONCE = re.compile(r"'nonce-([^']+)'")
PAGE_NONCE = re.compile(r'nonce="([^"]+)"')


def raw_page(client) -> str:
    return client.get(PATH).content.decode()


@pytest.fixture
def draws_holding_the_word(monkeypatch):
    """Django's random draws hold the word, as they do now and then: one level below the functions
    that ``fixed_response_tokens`` replaces, so a draw only reaches the page without that fixture."""
    monkeypatch.setattr(
        "django.middleware.csrf.get_random_string", lambda length, **_: WORD.ljust(length, "a")
    )
    monkeypatch.setattr(
        "django.utils.csp.secrets", SimpleNamespace(token_urlsafe=lambda nbytes: f"{WORD}-x")
    )


def test_a_scan_of_the_raw_page_does_not_depend_on_the_draw(client, draws_holding_the_word):
    assert WORD not in raw_page(client)


class TestTheRealTokens:
    """With the random tokens of production: what says that fixing their value hides nothing."""

    @pytest.fixture
    def fixed_response_tokens(self):
        """Overrides the autouse fixture of conftest.py for this class."""

    def test_the_draw_does_reach_the_page(self, client, draws_holding_the_word):
        """Control of the test above: without the fixed tokens, the same draw is a red."""
        html = raw_page(client)

        assert f'nonce="{WORD}-x"' in html
        assert f'name="csrfmiddlewaretoken" value="{WORD}' in html

    def test_every_response_brings_its_own_nonce_in_the_header_and_in_the_page(self, client):
        """All the nonces of the page are the header's: under the fixed value, a second one drawn
        for part of the page looks the same, and the comparisons of test_templates.py cannot see it."""
        responses = [client.get(PATH), client.get(PATH)]
        nonces = [
            HEADER_NONCE.search(response.headers["Content-Security-Policy"]).group(1)
            for response in responses
        ]

        assert nonces[0] != nonces[1]
        for response, nonce in zip(responses, nonces):
            assert set(PAGE_NONCE.findall(response.content.decode())) == {nonce}

    def test_every_page_brings_its_own_csrf_token(self, client):
        first, second = (CSRF_INPUT.search(raw_page(client)).group(1) for _ in range(2))

        assert first != second
