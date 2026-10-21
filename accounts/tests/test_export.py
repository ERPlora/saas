"""Account → Profile → «Download my data»: ``accounts.data.export`` (ACCOUNTS-F26; GDPR art. 20).

Ported from ERPlora/saas ``apps/dashboard/settings`` (``export_data``, origin/develop) and its flows
SAAS_DASHBOARD-F207 and the feature «API — Exportar mis datos»: one machine-readable file (JSON) with what the
account is and what it did here — its details, preferences and photo, its addresses and the Google account
linked to it, its open sessions and API keys (never their secret), the businesses it belongs to and ERPlora's
invoices it sees, each with its recipient as on its issue date. Nothing of another account (the tenancy test).
The old file also carried the vendor's modules and earnings: there is no marketplace here.
"""

import json
from datetime import date

import pytest
from allauth.socialaccount.models import SocialAccount
from django.test import Client

from accounts import queries
from accounts.models import ApiKey, ProfilePhoto, UserPreferences
from accounts.schemas import DataExportIn
from accounts.tests.conftest import ctx_for, api_get, sign_in
from billing.tests.test_invoice_queries import issue
from hubs.tests.conftest import create_business, plans  # noqa: F401 - the plans fixture

pytestmark = pytest.mark.django_db

EXPORT = "/api/accounts/export"


def _export(user) -> dict:
    return queries.data_export(ctx_for(user), DataExportIn()).model_dump(mode="json")


@pytest.fixture
def bea(django_user_model, password):
    return django_user_model.objects.create_user(
        email="bea@example.com", password=password, first_name="Bea", last_name="Ruiz", language="en"
    )


class TestWhatTheFileCarries:
    def test_the_account_its_preferences_and_its_photo(self, ana):
        UserPreferences.objects.create(user=ana, theme_mode="dark", hub_alerts=False)
        ProfilePhoto.objects.create(user=ana, content_type="image/png", data=b"\x89PNG")

        data = _export(ana)

        assert data["format"] == "erplora.account-export"
        assert data["version"] == 1
        assert data["account"]["email"] == "ana@example.com"
        assert (data["account"]["first_name"], data["account"]["last_name"]) == ("Ana", "García")
        assert data["account"]["language"] == "es"
        assert data["account"]["has_password"] is True
        assert data["preferences"] == {"theme_mode": "dark", "language": "es", "hub_alerts": False}
        assert data["photo"].startswith("data:image/png;base64,")

    def test_an_account_that_never_chose_carries_the_defaults_and_no_photo(self, ana):
        data = _export(ana)

        assert data["preferences"] == {"theme_mode": "system", "language": "es", "hub_alerts": True}
        assert data["photo"] is None

    def test_the_terms_it_accepted(self, ana):
        from accounts.services import accept_legal_texts

        accept_legal_texts(sender=None, user=ana)

        terms = _export(ana)["account"]["terms"]
        assert terms["accepted_at"] is not None
        assert terms["terms_version"] and terms["privacy_version"]

    def test_its_addresses_and_the_google_account_linked_to_it(self, ana):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=ana, email=ana.email, verified=True, primary=True)
        SocialAccount.objects.create(user=ana, provider="google", uid="108-ana")

        data = _export(ana)

        assert data["email_addresses"] == [{"email": "ana@example.com", "verified": True, "primary": True}]
        assert [(row["provider"], row["uid"]) for row in data["connected_accounts"]] == [("google", "108-ana")]

    def test_its_open_sessions(self, ana, password):
        sign_in(Client(), ana.email, password)

        sessions = _export(ana)["sessions"]

        assert len(sessions) == 1
        assert {"ip", "browser", "device", "created_at", "last_seen_at"} <= set(sessions[0])

    def test_its_api_keys_revoked_ones_too_never_their_secret(self, ana):
        secret, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=ana, name="Contabilidad", prefix=prefix, key_hash=key_hash, scopes=["hubs.read"])

        data = _export(ana)
        text = json.dumps(data)

        assert [(row["name"], row["scopes"]) for row in data["api_keys"]] == [("Contabilidad", ["hubs.read"])]
        assert key_hash not in text and secret not in text

    def test_its_businesses_with_its_role(self, ana, plans):  # noqa: F811
        create_business(ana, name="Panadería López")

        businesses = _export(ana)["businesses"]

        # The role as hubs names it (the prefixed customer roles, accounts 0002).
        assert [(row["name"], row["role"]) for row in businesses] == [("Panadería López", "hub_owner")]

    def test_erploras_invoices_with_their_recipient_as_issued(self, ana, plans):  # noqa: F811
        business = create_business(ana, name="Panadería López")
        issue(business, 7, on=date(2026, 9, 1), payer=ana, payer_tax_id="B12345678")

        invoices = _export(ana)["invoices"]

        assert [row["number"] for row in invoices] == ["ERP-2026-00007"]
        assert invoices[0]["recipient"]["tax_id"] == "B12345678"
        assert invoices[0]["total_cents"] == 3629
        assert [line["description"] for line in invoices[0]["lines"]] == ["1 × Starter"]

    def test_reading_it_writes_nothing(self, ana):
        before = UserPreferences.objects.count()

        _export(ana)

        assert UserPreferences.objects.count() == before


class TestNothingOfAnotherAccount:
    def test_another_accounts_business_invoice_key_session_and_address_stay_out(self, ana, bea, password, plans):  # noqa: F811
        business = create_business(bea, name="Bodega Bea")
        issue(business, 9, payer=bea, payer_tax_id="X9999999Z")
        _, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=bea, name="Llave de Bea", prefix=prefix, key_hash=key_hash)
        sign_in(Client(), bea.email, password)
        SocialAccount.objects.create(user=bea, provider="google", uid="108-bea")

        text = json.dumps(_export(ana))

        for foreign in ("bea@example.com", "Bodega Bea", "X9999999Z", "Llave de Bea", prefix, "108-bea", str(bea.pk)):
            assert foreign not in text


class TestOverHttp:
    def test_the_file_comes_as_json_for_the_signed_in_account(self, signed_in, ana):
        response = api_get(signed_in, EXPORT)

        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/json")
        assert response.json()["account"]["email"] == "ana@example.com"

    def test_an_anonymous_visitor_gets_the_401_envelope(self, client):
        response = api_get(client, EXPORT)

        assert (response.status_code, response.json()["error"]["code"]) == (401, "unauthorized")

    def test_an_api_key_never_downloads_the_account(self, client, ana):
        secret, prefix, key_hash = ApiKey.new_secret()
        ApiKey.objects.create(user=ana, name="k", prefix=prefix, key_hash=key_hash, scopes=["hubs.read", "billing.read"])

        response = client.get(EXPORT, HTTP_HOST="localhost:8001", HTTP_AUTHORIZATION=f"Bearer {secret}")

        assert (response.status_code, response.json()["error"]["code"]) == (403, "api_key_not_allowed")
