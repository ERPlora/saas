"""The context builder of saas-next: the scope is the signed-in user (PLAN §14.1, «SaaS → usuario»).

Built from the request, never from the payload; refreshed before every live re-run, so a deleted or
deactivated account loses its stream.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from live.context import OperationContext, Scope, get_builder
from live.errors import Unauthorized

from base.operations import ANONYMOUS_KEY, UserContextBuilder, UserScopeResolver


def request_for(user=None, language: str = "en"):
    request = RequestFactory().get("/", HTTP_HOST="localhost:8001")
    request.user = user if user is not None else AnonymousUser()
    request.LANGUAGE_CODE = language
    return request


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
def test_a_signed_in_request_acts_as_its_user_with_no_permission_yet(ana):
    ctx = UserContextBuilder().from_request(request_for(ana))

    assert (ctx.actor, ctx.scope, ctx.permissions) == (
        ana,
        Scope("user", str(ana.pk)),
        frozenset(),
    )


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


def test_refresh_of_an_anonymous_context():
    builder = UserContextBuilder()
    ctx = builder.from_request(request_for())

    assert builder.refresh(ctx) == ctx
