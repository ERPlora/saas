"""The context builder of saas-next: the scope is the signed-in user (PLAN §14.1, «SaaS → usuario»).

Built from the request, never from the payload; refreshed before every live re-run, so a deleted or
deactivated account, or a session that ended (a sign-out, «Close the other sessions», a new password),
loses its stream.
"""

import json
from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import Client, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import translation
from live.context import OperationContext, Scope, get_builder
from live.errors import Unauthorized
from live.executor import BYE_FRAME, Executor, Stream, Subscription
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get as get_operation

from accounts.tests.conftest import BROWSER, HOST, api_post, sign_in
from base.operations import ACCOUNT_ROLE, ANONYMOUS_KEY, UserContextBuilder, UserScopeResolver

NEW_PASSWORD = "a brand new pass phrase 2026"


def request_for(user=None, language: str = "en", session=None):
    request = RequestFactory().get("/", HTTP_HOST="localhost:8001")
    request.user = user if user is not None else AnonymousUser()
    request.LANGUAGE_CODE = language
    if session is not None:
        request.session = session
    return request


def browser_session(browser):
    """The session a browser's ``/api/live`` stream opens with: its cookie's, read once when the stream starts
    (``AuthenticationMiddleware``), as the stream then holds it for as long as it lives."""
    session = import_module(settings.SESSION_ENGINE).SessionStore(session_key=browser.session.session_key)
    assert session.get(SESSION_KEY) is not None
    return session


def end_by_deleting(browser, ana, password):
    import_module(settings.SESSION_ENGINE).SessionStore(session_key=browser.session.session_key).delete()


def end_by_signing_out_in_another_tab(browser, ana, password):
    """The same browser (same cookie) signs out in another tab: allauth.headless's ``DELETE auth/session``."""
    assert browser.delete(f"{BROWSER}/auth/session", HTTP_HOST=HOST).status_code == 401


def end_by_closing_the_others_elsewhere(browser, ana, password):
    """Another browser's «Close the other sessions» (Account → Security); that browser is returned."""
    other = sign_in(Client(), ana.email, password)
    assert api_post(other, "/api/accounts/sessions/close_others").status_code == 200
    return other


def end_by_a_new_password_elsewhere(browser, ana, password):
    """Another browser changes the password (returned): Django keeps this session's row, but it was opened with the
    old password."""
    other = sign_in(Client(), ana.email, password)
    response = other.post(
        f"{BROWSER}/account/password/change",
        {"current_password": password, "new_password": NEW_PASSWORD},
        content_type="application/json",
        HTTP_HOST=HOST,
    )
    assert response.status_code == 200, response.content
    return other


ENDINGS = [
    end_by_deleting,
    end_by_signing_out_in_another_tab,
    end_by_closing_the_others_elsewhere,
    end_by_a_new_password_elsewhere,
]


def test_settings_point_at_this_builder():
    assert isinstance(get_builder(), UserContextBuilder)


@pytest.mark.django_db
def test_the_scope_of_a_signed_in_request_is_its_user(ana):
    assert UserScopeResolver().resolve(request_for(ana)) == Scope("user", str(ana.pk))


def test_an_anonymous_request_has_the_anonymous_scope():
    assert UserScopeResolver().resolve(request_for()) == Scope("user", ANONYMOUS_KEY)


def test_an_anonymous_request_has_no_actor_and_keeps_its_language():
    request = request_for(language="es")

    ctx = UserContextBuilder().from_request(request)

    assert ctx == OperationContext(
        scope=Scope("user", ANONYMOUS_KEY),
        actor=None,
        permissions=frozenset(),
        language="es",
        request=request,
    )


@pytest.mark.django_db
def test_a_signed_in_request_acts_as_its_user_with_the_account_role(ana):
    """The panel's apps grant the role ``account`` their permissions (``role_permissions``); who
    may act on a business is checked inside each operation, by the account's role there."""
    ctx = UserContextBuilder().from_request(request_for(ana))

    assert (ctx.actor, ctx.scope) == (ana, Scope("user", str(ana.pk)))
    assert ctx.permissions == permissions_for_role(all_live_app_configs(), ACCOUNT_ROLE)
    assert {"hubs.view", "hubs.manage"} <= ctx.permissions


def test_an_anonymous_request_holds_no_permission():
    assert UserContextBuilder().from_request(request_for()).permissions == frozenset()


@pytest.mark.django_db
def test_refresh_rereads_the_user(ana):
    builder = UserContextBuilder()
    ctx = builder.from_request(request_for(ana))
    type(ana).objects.filter(pk=ana.pk).update(first_name="Anabel")

    assert builder.refresh(ctx).actor.first_name == "Anabel"


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["deactivated", "deleted"])
def test_refresh_of_a_user_that_is_gone_ends_the_stream(ana, change):
    builder = UserContextBuilder()
    ctx = builder.from_request(request_for(ana))
    users = type(ana).objects.filter(pk=ana.pk)
    if change == "deleted":
        users.delete()
    else:
        users.update(is_active=False)

    # The executor answers Unauthorized with `bye`: the stream closes.
    with pytest.raises(Unauthorized):
        builder.refresh(ctx)


@pytest.mark.django_db
def test_the_end_of_a_stream_speaks_its_language(ana):
    builder = UserContextBuilder()
    ctx = builder.from_request(request_for(ana))
    type(ana).objects.filter(pk=ana.pk).update(is_active=False)

    with translation.override("es"), pytest.raises(Unauthorized) as refused:
        builder.refresh(ctx)

    assert refused.value.message == "La cuenta ya no está activa."


def test_refresh_of_an_anonymous_context():
    builder = UserContextBuilder()
    ctx = builder.from_request(request_for())

    assert builder.refresh(ctx) == ctx


@pytest.mark.django_db
class TestASessionThatEnded:
    """A stream lives on the session it opened with; once that session ends, its next re-run ends it (``bye``,
    401 ``base.session_ended``, the Hub's code, hub#190), and ``@erplora/ui`` takes the tab to the sign-in (ui#25)."""

    @pytest.fixture
    def browser(self, ana, password):
        return sign_in(Client(), ana.email, password)

    @pytest.fixture
    def ctx(self, browser, ana):
        return UserContextBuilder().from_request(request_for(ana, session=browser_session(browser)))

    def test_a_live_session_goes_on_and_speaks_the_account_language(self, ctx, ana):
        type(ana).objects.filter(pk=ana.pk).update(language="es")

        refreshed = UserContextBuilder().refresh(ctx)

        assert (refreshed.actor.pk, refreshed.language) == (ana.pk, "es")

    @pytest.mark.parametrize("end", ENDINGS, ids=lambda end: end.__name__)
    def test_its_next_run_ends_the_stream(self, end, browser, ctx, ana, password):
        end(browser, ana, password)

        with pytest.raises(Unauthorized) as ended:
            UserContextBuilder().refresh(ctx)

        assert (ended.value.status, ended.value.code) == (401, "base.session_ended")

    @pytest.mark.parametrize("end", ENDINGS[2:], ids=lambda end: end.__name__)
    def test_the_session_that_ended_the_others_goes_on(self, end, browser, ana, password):
        """The browser that closed the others or changed the password keeps its own stream (Django gives the one that
        changed it a new key: its cookie's, which its stream reopens with)."""
        other = end(browser, ana, password)
        ctx = UserContextBuilder().from_request(request_for(ana, session=browser_session(other)))

        assert UserContextBuilder().refresh(ctx).actor.pk == ana.pk

    def test_a_rotated_secret_key_ends_no_session(self, ctx, settings):
        """A new ``SECRET_KEY`` with the old one among its fallbacks still signs in the sessions opened before (Django
        renews their hash at their next request): their streams go on."""
        settings.SECRET_KEY_FALLBACKS = [settings.SECRET_KEY]
        settings.SECRET_KEY = "a-new-secret-key-for-this-test-only-0123456789abcdef"

        assert UserContextBuilder().refresh(ctx).actor == ctx.actor

    def test_the_end_speaks_the_stream_language(self, browser, ctx, ana, password):
        end_by_deleting(browser, ana, password)

        with translation.override("es"), pytest.raises(Unauthorized) as ended:
            UserContextBuilder().refresh(ctx)

        assert ended.value.message == "Tu sesión ha terminado: vuelve a entrar."

    def test_reading_the_session_costs_one_query_per_run(self, ctx):
        """``refresh`` runs before every live re-run: the account and its session, one query each."""
        with CaptureQueriesContext(connection) as queries:
            UserContextBuilder().refresh(ctx)

        assert len(queries) == 2, [query["sql"] for query in queries]

    def test_the_stream_says_bye_instead_of_a_new_result(self, browser, ctx, ana, password):
        """The executor's own run (``/api/live``): a result while the session lives, ``bye`` once it ended."""
        op = get_operation("base.session.me")
        stream = Stream(ctx)
        sub = Subscription("me", op, op.input())
        alive = Executor()._run_in_language(stream, sub)
        assert alive.startswith(b"event: result\n") and json.loads(alive.split(b"data: ", 1)[1])["data"]["user"]

        end_by_signing_out_in_another_tab(browser, ana, password)

        assert Executor()._run_in_language(stream, sub) == BYE_FRAME
