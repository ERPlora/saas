"""IndexNow: telling Bing (and so ChatGPT search) the same day, not next month (spec §8.2).

Ported from ERPlora/saas ``landing/indexnow.py`` and ``landing/tests/test_indexnow.py``
(origin/develop c5ca8ca). Two halves, both needed or the protocol rejects everything: the key file
at ``/<key>.txt`` (proof we control the domain) and the submission carrying the same key and only
URLs on our host.

Not ported: ``TestItActuallyRuns`` (the Celery task and its beat entry). saas-next has no Celery;
the daily run becomes a scheduled ECS task with ``indexnow_submit`` (PLAN §16.5, plan §7).
"""

import pytest
import requests

from public import indexnow
from public.crawlers import private_prefixes
from public.sitemaps import StaticPagesSitemap

KEY = "0123456789abcdef0123456789abcdef"
HOST = "localhost:8001"

# The submission reads the sitemaps, and the store's read the catalog from the database (L6).
pytestmark = pytest.mark.django_db


class _Answer:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def a_public_page(monkeypatch):
    """A page in the static sitemap: llms.txt stands in for any public page."""
    monkeypatch.setattr(StaticPagesSitemap, "pages", (("public:llms_txt", 0.7),))


@pytest.fixture
def sent(monkeypatch):
    """The calls to IndexNow's API, answered 200."""
    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append(
            {"url": url, "payload": json, "timeout": timeout, "headers": headers}
        )
        return _Answer(200)

    monkeypatch.setattr(indexnow.requests, "post", fake_post)
    return calls


# The key file


@pytest.mark.django_db
def test_the_key_file_is_served_at_the_key_path(client, settings):
    settings.INDEXNOW_KEY = KEY

    response = client.get(f"/{KEY}.txt", HTTP_HOST=HOST)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert response.content.decode() == KEY


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
def test_another_key_is_not_served(client, settings):
    """Only OUR key: a wildcard would hand anyone a verified key file for our domain."""
    settings.INDEXNOW_KEY = KEY

    assert (
        client.get("/ffffffffffffffffffffffffffffffff.txt", HTTP_HOST=HOST).status_code
        == 404
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
def test_without_a_key_nothing_is_served(client, settings):
    settings.INDEXNOW_KEY = ""

    assert client.get(f"/{KEY}.txt", HTTP_HOST=HOST).status_code == 404


@pytest.mark.django_db
def test_the_key_ships_with_the_code(client, settings):
    """IndexNow keys are public by design: a default makes the feature work the moment it
    deploys; ``INDEXNOW_KEY`` still overrides it."""
    assert settings.INDEXNOW_KEY.isalnum()
    assert len(settings.INDEXNOW_KEY) >= 8
    assert (
        client.get(f"/{settings.INDEXNOW_KEY}.txt", HTTP_HOST=HOST).status_code == 200
    )


# The submission


@pytest.mark.usefixtures("a_public_page")
def test_it_posts_the_sitemap_urls_with_the_key(settings, sent):
    settings.INDEXNOW_KEY = KEY

    submitted = indexnow.submit_sitemap_urls(host="erplora.com")

    (call,) = sent
    assert call["url"] == "https://api.indexnow.org/indexnow"
    assert call["payload"] == {
        "host": "erplora.com",
        "key": KEY,
        "keyLocation": f"https://erplora.com/{KEY}.txt",
        "urlList": ["https://erplora.com/llms.txt"],
    }
    assert call["timeout"] == indexnow.TIMEOUT_SECONDS
    assert submitted == 1


def test_every_submitted_url_is_on_our_own_host(settings, sent, monkeypatch):
    """IndexNow rejects the WHOLE batch if one URL is off-host."""
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(
        StaticPagesSitemap,
        "pages",
        (("public:llms_txt", 0.7), ("public:robots_txt", 0.1)),
    )

    indexnow.submit_sitemap_urls(host="erplora.com")

    for url in sent[0]["payload"]["urlList"]:
        assert url.startswith("https://erplora.com/")


def test_the_private_half_is_never_submitted(settings, sent, monkeypatch, caplog):
    """Submitting is the loudest way to publish a URL: the last gate drops a private one."""
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(
        StaticPagesSitemap, "pages", (("public:llms_txt", 0.7), ("hub_login", 0.1))
    )

    indexnow.submit_sitemap_urls(host="erplora.com")

    urls = sent[0]["payload"]["urlList"]
    assert urls == ["https://erplora.com/llms.txt"]
    assert not any(
        url.removeprefix("https://erplora.com").startswith(private_prefixes())
        for url in urls
    )
    assert any("/hub-login/" in record.getMessage() for record in caplog.records)


@pytest.mark.usefixtures("a_public_page")
def test_without_a_key_nothing_is_posted(settings, monkeypatch):
    settings.INDEXNOW_KEY = ""

    def explode(*args, **kwargs):
        raise AssertionError("posted to IndexNow with no key configured")

    monkeypatch.setattr(indexnow.requests, "post", explode)

    assert indexnow.submit_sitemap_urls(host="erplora.com") == 0


def test_without_pages_nothing_is_posted_and_it_says_so(settings, monkeypatch, caplog):
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(StaticPagesSitemap, "pages", ())

    def explode(*args, **kwargs):
        raise AssertionError("posted an empty batch")

    monkeypatch.setattr(indexnow.requests, "post", explode)

    assert indexnow.submit_sitemap_urls(host="erplora.com") == 0
    assert any("no URLs" in record.getMessage() for record in caplog.records)


@pytest.mark.usefixtures("a_public_page")
def test_a_rejected_submission_is_reported_not_swallowed(settings, monkeypatch, caplog):
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(
        indexnow.requests,
        "post",
        lambda url, json, timeout, headers: _Answer(422, "Unprocessable"),
    )

    assert indexnow.submit_sitemap_urls(host="erplora.com") == 0
    assert any(
        "422" in record.getMessage() and record.levelname == "ERROR"
        for record in caplog.records
    )


@pytest.mark.usefixtures("a_public_page")
def test_an_unreachable_api_is_reported_not_swallowed(settings, monkeypatch, caplog):
    settings.INDEXNOW_KEY = KEY

    def unreachable(url, json, timeout, headers):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(indexnow.requests, "post", unreachable)

    assert indexnow.submit_sitemap_urls(host="erplora.com") == 0
    assert any(
        "no route to host" in record.getMessage() and record.levelname == "ERROR"
        for record in caplog.records
    )
