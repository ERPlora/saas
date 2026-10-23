"""``manage.py indexnow_submit``: the daily push to IndexNow (ported from ERPlora/saas
``landing/management/commands/indexnow_submit.py`` and its test, origin/develop c5ca8ca).

It runs every day in a scheduled ECS task whose only alarm is a non-zero exit (aws ``task_failed``),
so its three endings are part of the contract (PUBLIC-F14): submitted (0), no key configured (0, a
legitimate state in development, with a warning) and rejected or unanswered (``CommandError``)."""

import logging
from io import StringIO

import pytest
import requests
from django.core.management import ManagementUtility, call_command
from django.core.management.base import CommandError

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


def test_indexnow_refuses_to_submit_outside_prod(settings, sent):
    """pre.erplora.com (plan 2026-10-14-entorno-pre) is never announced to a search engine."""
    settings.INDEXNOW_KEY = KEY
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.PUBLIC_HOST = "pre.erplora.com"

    with pytest.raises(CommandError, match="pre"):
        call_command("indexnow_submit", stdout=StringIO())

    assert sent == []


@pytest.fixture
def a_public_page(monkeypatch):
    monkeypatch.setattr(StaticPagesSitemap, "pages", (("public:llms_txt", 0.7),))


def _answered(status_code, text=""):
    def fake_post(url, json, timeout, headers):
        return type("Answer", (), {"status_code": status_code, "text": text})()

    return fake_post


def _unanswered(error):
    def fake_post(url, json, timeout, headers):
        raise error

    return fake_post


@pytest.mark.usefixtures("a_public_page")
@pytest.mark.parametrize("status_code", [400, 403, 422, 429, 500, 503])
def test_a_rejected_submission_fails_the_command(settings, monkeypatch, status_code):
    """Only a failed exit reaches the alarm: a rejected batch must not end like a quiet day."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(indexnow.requests, "post", _answered(status_code))

    with pytest.raises(CommandError, match=rf"\b{status_code}\b"):
        call_command("indexnow_submit", "--host", "erplora.com", stdout=StringIO())


@pytest.mark.usefixtures("a_public_page")
@pytest.mark.parametrize(
    "error",
    [
        requests.Timeout("read timed out"),
        requests.ConnectionError("no route to host"),
    ],
    ids=["timeout", "network"],
)
def test_an_unanswered_submission_fails_the_command(settings, monkeypatch, error):
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(indexnow.requests, "post", _unanswered(error))

    with pytest.raises(CommandError, match="did not reach"):
        call_command("indexnow_submit", "--host", "erplora.com", stdout=StringIO())


@pytest.mark.usefixtures("a_public_page")
@pytest.mark.parametrize(
    "fake_post",
    [
        _answered(403, f"Key {KEY} is not valid for this host"),
        _unanswered(requests.ConnectionError(f"payload with {KEY} never left")),
    ],
    ids=["rejected", "unanswered"],
)
def test_the_key_is_never_in_the_error_nor_in_the_log(
    settings, monkeypatch, caplog, fake_post
):
    """Even when the answer (or the library) echoes it back, the key stays out of what we write."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.INDEXNOW_KEY = KEY
    monkeypatch.setattr(indexnow.requests, "post", fake_post)
    out, err = StringIO(), StringIO()

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(CommandError) as failure,
    ):
        call_command("indexnow_submit", "--host", "erplora.com", stdout=out, stderr=err)

    assert KEY not in str(failure.value)
    assert KEY not in caplog.text
    assert KEY not in out.getvalue() + err.getvalue()
    assert caplog.records, "the failure must still be logged"


@pytest.mark.usefixtures("a_public_page")
def test_a_rejected_submission_exits_non_zero_from_manage_py(
    settings, monkeypatch, capsys
):
    """What the scheduled task sees: ``python manage.py indexnow_submit`` and its exit code."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.INDEXNOW_KEY = KEY
    settings.PUBLIC_HOST = "erplora.com"
    monkeypatch.setattr(indexnow.requests, "post", _answered(422, "Unprocessable"))
    root_handlers = list(logging.getLogger().handlers)
    argv = ["manage.py", "indexnow_submit"]

    # ``execute()`` minus its ``django.setup()``: the same command lookup and the same
    # ``run_from_argv`` that turns a ``CommandError`` into the process's exit code.
    with pytest.raises(SystemExit) as exit_:
        ManagementUtility(argv).fetch_command("indexnow_submit").run_from_argv(argv)

    assert exit_.value.code != 0
    assert "422" in capsys.readouterr().err
    # The process is set up once: logging rebuilt on this test's captured stderr would leave every
    # later test writing its log lines to a closed stream.
    assert logging.getLogger().handlers == root_handlers


@pytest.mark.usefixtures("a_public_page")
def test_without_a_key_it_warns_and_exits_cleanly(settings, monkeypatch):
    """No key is development's normal state: a warning, never an alarm, and nothing posted."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.INDEXNOW_KEY = ""

    def explode(*args, **kwargs):
        raise AssertionError("posted to IndexNow with no key configured")

    monkeypatch.setattr(indexnow.requests, "post", explode)
    out = StringIO()

    call_command("indexnow_submit", "--host", "erplora.com", stdout=out)

    assert "nothing submitted" in out.getvalue()
