"""``manage.py indexnow_submit``: the daily push to IndexNow (ported from ERPlora/saas
``landing/management/commands/indexnow_submit.py`` and its test, origin/develop c5ca8ca)."""

from io import StringIO

import pytest
from django.core.management import call_command

from public import indexnow
from public.sitemaps import StaticPagesSitemap

KEY = "0123456789abcdef0123456789abcdef"

# The submission reads the sitemaps, and the store's read the catalog from the database (L6).
pytestmark = pytest.mark.django_db


@pytest.fixture
def sent(monkeypatch):
    """A public page in the sitemap and the calls to IndexNow's API, answered 200."""
    monkeypatch.setattr(StaticPagesSitemap, "pages", (("public:llms_txt", 0.7),))
    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append(json)
        return type("Answer", (), {"status_code": 200, "text": ""})()

    monkeypatch.setattr(indexnow.requests, "post", fake_post)
    return calls


def test_it_submits_and_says_how_many(settings, sent):
    settings.INDEXNOW_KEY = KEY
    out = StringIO()

    call_command("indexnow_submit", "--host", "erplora.com", stdout=out)

    assert "IndexNow: 1 URLs submitted for erplora.com" in out.getvalue()


def test_it_submits_for_the_public_host_by_default(settings, sent):
    settings.INDEXNOW_KEY = KEY
    settings.PUBLIC_HOST = "erplora.com"

    call_command("indexnow_submit", stdout=StringIO())

    assert sent[0]["host"] == "erplora.com"


def test_it_never_looks_like_success_when_nothing_was_sent(settings):
    settings.INDEXNOW_KEY = ""
    out = StringIO()

    call_command("indexnow_submit", "--host", "erplora.com", stdout=out)

    assert "nothing submitted" in out.getvalue()
