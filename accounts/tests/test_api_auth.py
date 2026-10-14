"""An account's API key opens ``/api/`` (``accounts.api_auth``; plan 2026-10-13, L3-A; PLAN-SAAS §2.4).

Ported from ERPlora/saas ``apps/auth/apikeys/tests`` (``test_authentication``, ``test_permissions``,
``test_apps``) onto ninja. A key makes the request act as its account, bounded by its scopes, and only on the
operations declared with ``expose_api=True`` (opt-in, as in hub-next): ``<app>.read`` opens the app's queries,
``<app>.write`` its commands. Everything else of the API answers a key with 403 ``api_key_not_allowed``: a key
never manages the account nor mints keys. ``Authorization: Bearer erps_live_…`` (the convention of Stripe,
GitHub and OpenAI) and ``X-Api-Key`` (the hubs' header and the old SaaS's) are both read. Dropped: the hubs'
keys and ``X-Hub-Id`` (hub-next's, PLAN-SAAS §2.4), the environment check (one production).
"""

import logging
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from django.urls import path
from django.utils import timezone
from live.ninja import bind, run_operation
from live.operations import operation, registry
from ninja import Router

from accounts import api_auth, queries, services
from accounts.models import ApiKey
from accounts.tests.conftest import HOST
from accounts.tests.probe import queries as probe_queries
from accounts.tests.probe import services as probe_services
from accounts.tests.probe import urls as probe_urls
from config.api import api as saas_api
from config.api import build_api

pytestmark = pytest.mark.django_db

PROBES = {
    # name: (function, kind, exposed)
    "hubs.probe.list": (probe_queries.who, "query", True),
    "hubs.probe.touch": (probe_services.touch, "command", True),
    "billing.probe.list": (probe_queries.who, "query", True),
    "hubs.probe.secret": (probe_queries.who, "query", False),
    "hubs.probe.public": (probe_queries.who, "query", True),
}


def _declare(name, fn, kind, exposed):
    return operation(
        name,
        kind=kind,
        permission=None,
        input=probe_queries.ProbeIn,
        output=probe_queries.WhoOut,
        expose_api=exposed,
    )(fn)


@pytest.fixture
def probe_ops():
    declared = {name: _declare(name, *spec) for name, spec in PROBES.items()}
    yield declared
    for name in declared:
        registry.pop(name, None)


def _probe_api(ops):
    router = Router()

    @bind(router, "hubs.probe.list", "/hubs")
    async def hubs_list(request):
        return await run_operation(request, ops["hubs.probe.list"])

    @bind(router, "hubs.probe.touch", "/hubs/touch")
    async def hubs_touch(request):
        return await run_operation(request, ops["hubs.probe.touch"])

    @bind(router, "billing.probe.list", "/billing")
    async def billing_list(request):
        return await run_operation(request, ops["billing.probe.list"])

    @bind(router, "hubs.probe.secret", "/secret")
    async def secret(request):
        return await run_operation(request, ops["hubs.probe.secret"])

    @bind(router, "hubs.probe.public", "/public", auth=None)
    async def public(request):
        return await run_operation(request, ops["hubs.probe.public"])

    api = build_api(urls_namespace=f"accounts-api-auth-{uuid.uuid4().hex}")
    api.add_router("", router)
    return api


@pytest.fixture
def probe(settings, probe_ops):
    api = _probe_api(probe_ops)
    exposed = api_auth.install_api_key_auth(api)
    probe_urls.urlpatterns[:] = [path("api/", api.urls)]
    settings.ROOT_URLCONF = "accounts.tests.probe.urls"
    yield SimpleNamespace(api=api, exposed=exposed)
    probe_urls.urlpatterns.clear()


def _key(user, scopes=("hubs.read",), **fields):
    secret, prefix, key_hash = ApiKey.new_secret()
    key = ApiKey.objects.create(user=user, name="test", prefix=prefix, key_hash=key_hash, scopes=list(scopes), **fields)
    return key, secret


def _call(method, url, *, secret=None, header="bearer", client=None, **extra):
    client = client or Client(enforce_csrf_checks=True)
    if secret is not None:
        if header == "bearer":
            extra["HTTP_AUTHORIZATION"] = f"Bearer {secret}"
        else:
            extra["HTTP_X_API_KEY"] = secret
    if method == "get":
        return client.get(url, HTTP_HOST=HOST, **extra)
    return client.post(url, {}, content_type="application/json", HTTP_HOST=HOST, **extra)


class TestWithoutAKey:
    def test_the_session_still_answers_and_an_anonymous_visitor_gets_401(self, probe, ana):
        assert _call("get", "/api/hubs").json()["error"]["code"] == "unauthorized"
        client = Client()
        client.force_login(ana)
        assert _call("get", "/api/hubs", client=client).json() == {"email": "ana@example.com"}

    @pytest.mark.parametrize("extra", [{"HTTP_X_API_KEY": ""}, {"HTTP_AUTHORIZATION": "Basic YTpi"}])
    def test_an_empty_or_foreign_header_is_no_key(self, probe, extra):
        """Postman sends the header with the variable unset: empty means no key, the session gets its turn."""
        assert _call("get", "/api/hubs", **extra).json()["error"]["code"] == "unauthorized"


class TestAKeyOfAnAccount:
    @pytest.mark.parametrize("header", ["bearer", "x-api-key"])
    def test_the_request_acts_as_its_account(self, probe, ana, header):
        _, secret = _key(ana)

        response = _call("get", "/api/hubs", secret=secret, header=header)

        assert (response.status_code, response.json()) == (200, {"email": "ana@example.com"})

    def test_a_command_needs_no_csrf_token_with_a_key(self, probe, ana):
        """A browser never sends ``Authorization`` or ``X-Api-Key`` by itself: no cross-site request carries a key."""
        _, secret = _key(ana, scopes=["hubs.write"])

        assert _call("post", "/api/hubs/touch", secret=secret).status_code == 200

    @pytest.mark.parametrize(
        "secret",
        [
            "erps_live_" + "A" * 48,  # well-formed, nobody's
            "erps_live_short",
            "erpk_live_" + "A" * 48,  # a hub's key belongs to hub-next
            "not-a-key",
        ],
    )
    def test_a_wrong_key_is_401_with_its_own_code(self, probe, secret):
        response = _call("get", "/api/hubs", secret=secret)

        assert (response.status_code, response.json()["error"]["code"]) == (401, "api_key_invalid")

    def test_a_revoked_an_expired_and_a_deactivated_accounts_key_are_refused(self, probe, ana):
        now = timezone.now()
        _, revoked = _key(ana, revoked_at=now)
        _, expired = _key(ana, expires_at=now - timedelta(seconds=1))
        bo = get_user_model().objects.create_user(email="bo@example.com", password=None, is_active=False)
        _, inactive = _key(bo)

        for secret in (revoked, expired, inactive):
            assert _call("get", "/api/hubs", secret=secret).json()["error"]["code"] == "api_key_invalid"

    def test_a_key_that_still_works_is_found_in_time(self, probe, ana):
        _, secret = _key(ana, expires_at=timezone.now() + timedelta(days=1))

        assert _call("get", "/api/hubs", secret=secret).status_code == 200

    def test_garbage_costs_no_query(self, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert queries.api_key_for("erps_live_" + "-" * 48, timezone.now()) is None


class TestScopesBoundTheKey:
    def test_a_query_needs_the_apps_read(self, probe, ana):
        _, secret = _key(ana, scopes=["billing.read"])

        response = _call("get", "/api/hubs", secret=secret)

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "api_key_missing_scope"
        assert "hubs.read" in error["message"]
        assert _call("get", "/api/billing", secret=secret).status_code == 200

    def test_a_command_needs_the_apps_write(self, probe, ana):
        _, secret = _key(ana, scopes=["hubs.read"])

        response = _call("post", "/api/hubs/touch", secret=secret)

        assert (response.status_code, response.json()["error"]["code"]) == (403, "api_key_missing_scope")
        assert "hubs.write" in response.json()["error"]["message"]

    def test_an_operation_not_exposed_refuses_every_key(self, probe, ana):
        _, secret = _key(ana, scopes=["hubs.read", "hubs.write", "billing.read"])

        response = _call("get", "/api/secret", secret=secret)

        assert (response.status_code, response.json()["error"]["code"]) == (403, "api_key_not_allowed")

    def test_a_public_route_ignores_the_key(self, probe, ana):
        _, secret = _key(ana)

        assert _call("get", "/api/public", secret=secret).json() == {"email": None}

    def test_the_refusal_speaks_spanish(self, probe, ana):
        _, secret = _key(ana, scopes=["billing.read"])

        response = _call("get", "/api/hubs", secret=secret, HTTP_ACCEPT_LANGUAGE="es")

        assert response.json()["error"]["message"] == "A esta clave de API le falta el permiso que pide esta operación: hubs.read."


class TestUse:
    def test_the_last_use_is_recorded_and_not_rewritten_within_minutes(self, probe, ana):
        key, secret = _key(ana)

        _call("get", "/api/hubs", secret=secret)
        first = ApiKey.objects.get(pk=key.pk).last_used_at
        _call("get", "/api/hubs", secret=secret)

        assert first is not None
        assert ApiKey.objects.get(pk=key.pk).last_used_at == first

    def test_after_the_resolution_it_moves(self, probe, ana):
        key, secret = _key(ana, last_used_at=timezone.now() - services.API_KEY_LAST_USED_RESOLUTION)

        _call("get", "/api/hubs", secret=secret)

        assert ApiKey.objects.get(pk=key.pk).last_used_at > key.last_used_at

    def test_each_key_has_a_budget_per_minute(self, probe, ana, monkeypatch):
        monkeypatch.setattr(api_auth, "API_KEY_RATE", "2/m")
        _, secret = _key(ana)

        assert [_call("get", "/api/hubs", secret=secret).status_code for _ in range(3)] == [200, 200, 429]
        assert _call("get", "/api/hubs", secret=secret).json()["error"]["code"] == "rate_limited"

    def test_wrong_keys_from_one_address_are_cut_short(self, probe, monkeypatch):
        monkeypatch.setattr(api_auth, "INVALID_KEY_RATE", "2/m")
        wrong = "erps_live_" + "A" * 48

        assert [_call("get", "/api/hubs", secret=wrong).status_code for _ in range(3)] == [401, 401, 429]

    def test_a_refused_key_is_never_logged_whole(self, probe, caplog):
        caplog.set_level(logging.DEBUG)
        wrong = "erps_live_" + "B" * 48

        _call("get", "/api/hubs", secret=wrong)

        assert wrong not in caplog.text


class TestTheSaasApi:
    """The real ``/api/``: no operation of the SaaS is exposed yet, so a key opens none of it (hubs and billing
    choose theirs with ``expose_api=True``); above all, a key never manages the account or its keys."""

    @pytest.mark.parametrize(
        "method, url",
        [
            ("get", "/api/accounts/profile"),
            ("get", "/api/accounts/api-keys"),
            ("post", "/api/accounts/api-keys"),
            ("post", "/api/accounts/profile/delete"),
        ],
    )
    def test_a_key_never_manages_the_account(self, ana, method, url):
        _, secret = _key(ana, scopes=["hubs.read", "hubs.write", "billing.read"])

        response = _call(method, url, secret=secret)

        assert (response.status_code, response.json()["error"]["code"]) == (403, "api_key_not_allowed")
        assert get_user_model().objects.filter(pk=ana.pk).exists()

    def test_a_public_route_ignores_the_key(self, ana):
        _, secret = _key(ana)

        assert _call("get", "/api/me", secret=secret).json()["user"] is None

    def test_the_session_is_untouched(self, signed_in):
        assert signed_in.get("/api/accounts/profile", HTTP_HOST=HOST).status_code == 200

    def test_every_route_with_auth_reads_keys(self):
        from live.ninja import _routes

        for full_path, route in _routes(saas_api):
            if route.auth_callbacks:
                assert route.auth_callbacks[0] is api_auth.refuse_api_keys or isinstance(
                    route.auth_callbacks[0], api_auth.ApiKeyBearer
                ), full_path


class TestInstalling:
    def test_it_returns_the_exposed_operations(self, probe):
        assert sorted(probe.exposed) == ["billing.probe.list", "hubs.probe.list", "hubs.probe.touch"]

    def test_the_openapi_names_both_headers_on_the_exposed_operations_only(self, probe, client):
        schema = client.get("/api/openapi.json", HTTP_HOST=HOST).json()

        assert schema["components"]["securitySchemes"]["ApiKeyBearer"] == {"type": "http", "scheme": "bearer"}
        assert schema["components"]["securitySchemes"]["ApiKeyHeader"] == {
            "type": "apiKey",
            "in": "header",
            "name": "X-Api-Key",
        }
        assert {"ApiKeyBearer": []} in schema["paths"]["/api/hubs"]["get"]["security"]
        assert schema["paths"]["/api/secret"]["get"]["security"] == [{"SessionAuth": []}]

    def test_exposing_an_operation_no_scope_opens_fails_at_start(self, probe_ops):
        accounts_op = _declare("accounts.probe.list", probe_queries.who, "query", True)
        try:
            router = Router()

            @bind(router, "accounts.probe.list", "/mine")
            async def mine(request):
                return await run_operation(request, accounts_op)

            api = build_api(urls_namespace=f"accounts-api-auth-{uuid.uuid4().hex}")
            api.add_router("", router)

            with pytest.raises(ImproperlyConfigured, match="accounts.read"):
                api_auth.install_api_key_auth(api)
        finally:
            registry.pop("accounts.probe.list", None)
