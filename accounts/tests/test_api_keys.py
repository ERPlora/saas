"""Account → API keys: ``accounts.apikey.list``, ``accounts.apikey.create`` and ``accounts.apikey.revoke``
(plan 2026-10-13, L3-A; PLAN-SAAS §2.4: the SaaS keeps the account's keys, the hubs' are hub-next's).

Ported from ERPlora/saas ``apps/auth/apikeys/tests`` (80): the key shown once and kept as a hash, its scopes,
its expiry and last use, revoking as the audit trail. Changed: the account issues its own keys from the panel
(the original issued them only from the console, a superuser for a staff account), with a recent sign-in, as
GitHub, Stripe and Shopify do; the expiry is 30 or 90 days or never (90 by default, the mockup's). Dropped,
with their reason: the hubs' keys and their grace (hub-next's, PLAN-SAAS §2.4), the ``pre`` environment (one
production), the vendor and fleet scopes (the developer part left, PLAN-SAAS §3.6 point 2) and the mint script.
How a key opens the API is ``test_api_auth.py``.
"""

import logging
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from live.live_registry import live_registry

from accounts import events, services
from accounts.models import API_KEY_PREFIX, ApiKey
from accounts.tests.conftest import HOST, api_get, api_post

pytestmark = pytest.mark.django_db

KEYS = "/api/accounts/api-keys"
REVOKE = "/api/accounts/api-keys/revoke"


def _create(client, **body):
    return api_post(client, KEYS, {"name": "Zapier", "scopes": ["hubs.read"], **body})


class TestCreating:
    def test_the_secret_comes_once_and_only_its_hash_is_kept(self, signed_in, ana):
        response = _create(signed_in)

        assert response.status_code == 201
        body = response.json()
        secret = body["secret"]
        assert secret.startswith(API_KEY_PREFIX) and len(secret) == len(API_KEY_PREFIX) + 48
        key = ApiKey.objects.get(user=ana)
        assert key.key_hash == ApiKey.hash_key(secret)
        assert secret not in {str(value) for value in vars(key).values()}
        assert body["key"]["prefix"] == secret[: len(API_KEY_PREFIX) + 8]
        assert (body["key"]["name"], body["key"]["scopes"], body["key"]["last_used_at"]) == ("Zapier", ["hubs.read"], None)

    def test_it_expires_in_90_days_unless_told_otherwise(self, signed_in, ana):
        before = timezone.now()

        _create(signed_in)
        _create(signed_in, name="Monthly", expires_in_days=30)
        _create(signed_in, name="Forever", expires_in_days=None)

        ends = {key.name: key.expires_at for key in ApiKey.objects.filter(user=ana)}
        assert timedelta(days=90) <= ends["Zapier"] - before < timedelta(days=90, minutes=1)
        assert timedelta(days=30) <= ends["Monthly"] - before < timedelta(days=30, minutes=1)
        assert ends["Forever"] is None

    @pytest.mark.parametrize(
        "body, field",
        [
            ({"expires_in_days": 60}, "expires_in_days"),
            ({"scopes": []}, "scopes"),
            ({"scopes": ["hubs.read", "fleet:promote"]}, "scopes"),
            ({"name": "   "}, "name"),
            ({"name": "x" * 121}, "name"),
        ],
    )
    def test_what_is_refused_is_a_422_on_its_field_and_nothing_is_created(self, signed_in, body, field):
        response = _create(signed_in, **body)

        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert not ApiKey.objects.exists()

    def test_an_unknown_scope_is_named(self, signed_in):
        response = _create(signed_in, scopes=["hubs.read", "fleet:promote"])

        assert "fleet:promote" in response.json()["error"]["fields"]["scopes"]

    def test_the_name_is_trimmed_and_the_scopes_kept_once_in_order(self, signed_in, ana):
        _create(signed_in, name="  Gestoría  ", scopes=["billing.read", "hubs.read", "billing.read"])

        key = ApiKey.objects.get(user=ana)
        assert (key.name, key.scopes) == ("Gestoría", ["billing.read", "hubs.read"])

    def test_an_old_sign_in_is_asked_for_the_password_and_nothing_is_created(self, signed_in_long_ago):
        response = _create(signed_in_long_ago)

        assert (response.status_code, response.json()["error"]["code"]) == (401, "reauthentication_required")
        assert not ApiKey.objects.exists()

    def test_an_account_that_only_signs_in_with_google_signs_in_with_google_again(self, client, ana):
        ana.set_unusable_password()
        ana.save()
        client.force_login(ana)

        response = _create(client)

        assert (response.status_code, response.json()["error"]["code"]) == (401, "reauthentication_required")
        assert not ApiKey.objects.exists()

    def test_a_request_with_an_api_key_never_counts_as_a_recent_sign_in(self, ana, rf):
        """Defence in depth (``api_auth`` already refuses keys here): a key is no sign-in."""
        import time

        from django.contrib.sessions.backends.db import SessionStore
        from live.errors import OperationError

        from accounts.tests.conftest import AUTHENTICATION_RECORDS, ctx_for

        _, prefix, key_hash = ApiKey.new_secret()
        key = ApiKey.objects.create(user=ana, name="k", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"])
        request = rf.post("/")
        request.session = SessionStore()
        request.session[AUTHENTICATION_RECORDS] = [{"method": "password", "at": time.time()}]
        request.user = ana
        request.auth = key

        with pytest.raises(OperationError) as refused:
            services.require_recent_authentication(ctx_for(ana, request=request))

        assert (refused.value.status, refused.value.code) == (403, "api_key_not_allowed")

    def test_an_account_has_a_ceiling_of_live_keys(self, signed_in, monkeypatch):
        monkeypatch.setattr(services, "MAX_ACTIVE_API_KEYS", 2)
        _create(signed_in, name="a")
        _create(signed_in, name="b")

        response = _create(signed_in, name="c")

        assert (response.status_code, response.json()["error"]["code"]) == (409, "accounts.api_key_limit")

    def test_a_revoked_or_expired_key_does_not_count(self, signed_in, ana, monkeypatch):
        monkeypatch.setattr(services, "MAX_ACTIVE_API_KEYS", 1)
        _create(signed_in, name="a")
        ApiKey.objects.update(revoked_at=timezone.now())

        assert _create(signed_in, name="b").status_code == 201
        ApiKey.objects.filter(name="b").update(expires_at=timezone.now())
        assert _create(signed_in, name="c").status_code == 201

    def test_the_account_is_told_by_mail_without_the_secret(self, english, signed_in, django_capture_on_commit_callbacks):
        """A new key is a new way into the account: its owner hears of it, as GitHub and Stripe do."""
        from django.core import mail

        with django_capture_on_commit_callbacks(execute=True):
            secret = _create(signed_in, name="Gestoría", scopes=["billing.read"]).json()["secret"]

        [message] = mail.outbox
        assert message.to == ["ana@example.com"]
        assert "Gestoría" in message.body and "Invoices · read" in message.body
        assert secret not in message.body and secret[:18] not in message.body

    def test_the_secret_is_never_logged(self, signed_in, caplog):
        caplog.set_level(logging.DEBUG)

        secret = _create(signed_in).json()["secret"]

        assert secret not in caplog.text

    def test_creating_re_runs_the_live_list(self, signed_in):
        from live.models import OutboxEvent

        _create(signed_in)

        assert list(OutboxEvent.objects.values_list("name", flat=True)) == [events.APIKEY_CREATED]
        assert "accounts.apikey.list" in live_registry.affected([events.APIKEY_CREATED])


class TestListing:
    def test_the_accounts_live_and_expired_keys_newest_first_without_secrets(self, signed_in, ana):
        _create(signed_in, name="Old")
        _create(signed_in, name="Expired")
        _create(signed_in, name="Revoked")
        _create(signed_in, name="New")
        ApiKey.objects.filter(name="Old").update(created_at=timezone.now() - timedelta(days=10))
        ApiKey.objects.filter(name="Expired").update(expires_at=timezone.now() - timedelta(days=1))
        ApiKey.objects.filter(name="Revoked").update(revoked_at=timezone.now())

        body = api_get(signed_in, KEYS).json()

        assert [(row["name"], row["expired"]) for row in body["rows"]] == [
            ("New", False),
            ("Expired", True),
            ("Old", False),
        ]
        assert body["total"] == 3
        assert set(body["rows"][0]) == {
            "id",
            "name",
            "prefix",
            "scopes",
            "created_at",
            "last_used_at",
            "expires_at",
            "expired",
        }

    def test_it_offers_the_scopes_with_what_they_open(self, english, signed_in):
        assert api_get(signed_in, KEYS).json()["scopes"] == [
            {"id": "hubs.read", "label": "Businesses · read"},
            {"id": "hubs.write", "label": "Businesses · write"},
            {"id": "billing.read", "label": "Invoices · read"},
        ]

    def test_in_spanish(self, signed_in):
        body = signed_in.get(KEYS, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").json()

        assert body["scopes"][0] == {"id": "hubs.read", "label": "Negocios · lectura"}

    def test_another_accounts_keys_are_not_listed(self, signed_in, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=bo, name="Bo's", prefix=prefix, key_hash=key_hash)

        assert api_get(signed_in, KEYS).json()["rows"] == []

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        assert api_get(client, KEYS).status_code == 401
        assert api_post(client, KEYS, {"name": "x", "scopes": ["hubs.read"]}).status_code == 401


class TestRevoking:
    def test_revoking_cuts_the_key_and_it_leaves_the_list_without_asking_the_password(self, signed_in_long_ago, ana):
        _, prefix, key_hash = ApiKey.new_secret()
        key_id = str(ApiKey.objects.create(user=ana, name="Zapier", prefix=prefix, key_hash=key_hash).pk)

        response = api_post(signed_in_long_ago, REVOKE, {"id": key_id})

        assert response.status_code == 200
        assert response.json()["id"] == key_id
        assert ApiKey.objects.get(pk=key_id).revoked_at is not None
        assert api_get(signed_in_long_ago, KEYS).json()["rows"] == []

    def test_revoking_twice_changes_nothing(self, signed_in):
        key_id = _create(signed_in).json()["key"]["id"]
        api_post(signed_in, REVOKE, {"id": key_id})
        first = ApiKey.objects.get(pk=key_id).revoked_at

        assert api_post(signed_in, REVOKE, {"id": key_id}).status_code == 200
        assert ApiKey.objects.get(pk=key_id).revoked_at == first

    def test_a_key_of_another_account_is_not_found(self, signed_in, password):
        bo = get_user_model().objects.create_user(email="bo@example.com", password=password)
        _, prefix, key_hash = ApiKey.new_secret()
        key = ApiKey.objects.create(user=bo, name="Bo's", prefix=prefix, key_hash=key_hash)

        response = api_post(signed_in, REVOKE, {"id": str(key.pk)})

        assert (response.status_code, response.json()["error"]["code"]) == (404, "not_found")
        assert ApiKey.objects.get(pk=key.pk).revoked_at is None

    def test_revoking_re_runs_the_live_list(self, signed_in):
        assert "accounts.apikey.list" in live_registry.affected([events.APIKEY_REVOKED])
