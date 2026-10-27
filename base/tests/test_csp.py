"""The SPA's Content Security Policy with Stripe (lot L2-D; PLAN-SAAS §3.6 point 17; plan §7 point 5).

Stripe.js is the ONE script the SaaS takes from another origin — PCI: it is never served by us — so the
SPA's policy (``settings.SECURE_CSP``, ``live.csp``) gains Stripe's origins for the Embedded Checkout, as
Stripe's security guide lists them for Checkout and Stripe.js, and nothing else: the nonce,
``'strict-dynamic'`` and Trusted Types stay, with no policy of Stripe's: the page's ``default`` policy
admits the script URLs of ``https://js.stripe.com`` (``createShell({ trustedScriptOrigins })``), so the
``trusted-types`` directive is ``live.csp``'s, untouched. The account
surface (``?surface=account``) sells nothing, so its page keeps the plain policy; so does every response
that is not the SPA's HTML (the API, the public web).
"""

import re

import pytest
from live.csp import base_policy

from base.csp import STRIPE_SOURCES, spa_policy

HOST = "localhost:8001"


def directives(header: str) -> dict[str, list[str]]:
    return {
        name: values
        for name, *values in (part.split() for part in header.split(";") if part.strip())
    }


class TestThePolicy:
    def test_stripe_s_origins_are_the_ones_its_guide_lists_for_checkout_and_stripe_js(self):
        assert STRIPE_SOURCES == {
            "script-src": ["https://js.stripe.com", "https://*.js.stripe.com", "https://checkout.stripe.com"],
            "frame-src": [
                "https://js.stripe.com",
                "https://*.js.stripe.com",
                "https://hooks.stripe.com",
                "https://checkout.stripe.com",
            ],
            "connect-src": [
                "https://api.stripe.com",
                "https://checkout.stripe.com",
                "https://merchant-ui-api.stripe.com",
            ],
            "img-src": ["https://*.stripe.com"],
        }

    def test_a_page_that_sells_adds_them_and_keeps_everything_else(self):
        base = base_policy()

        policy = spa_policy(base, sells=True)

        assert policy["script-src"] == [*base["script-src"], *STRIPE_SOURCES["script-src"]]
        assert policy["connect-src"] == [*base["connect-src"], *STRIPE_SOURCES["connect-src"]]
        assert policy["img-src"] == [*base["img-src"], *STRIPE_SOURCES["img-src"]]
        # No frame-src of its own before: it starts from default-src, so same-origin frames still load.
        assert policy["frame-src"] == [*base["default-src"], *STRIPE_SOURCES["frame-src"]]
        # Trusted Types are the page's own: `default` admits Stripe.js's script URLs, no extra policy.
        assert policy["trusted-types"] == base["trusted-types"]
        untouched = set(base) - set(STRIPE_SOURCES)
        assert {name: policy[name] for name in untouched} == {name: base[name] for name in untouched}

    def test_nothing_else_comes_from_another_origin(self):
        base = base_policy()

        policy = spa_policy(base, sells=True)

        added = {
            source
            for name, sources in policy.items()
            for source in sources
            if source not in base.get(name, base["default-src"])
        }
        assert {source for source in added if source.startswith("https://")} <= {
            source for sources in STRIPE_SOURCES.values() for source in sources
        }
        assert added == {source for sources in STRIPE_SOURCES.values() for source in sources}

    def test_without_trusted_types_it_adds_none(self):
        debug = base_policy()
        del debug["trusted-types"]

        assert "trusted-types" not in spa_policy(debug, sells=True)

    def test_a_page_that_sells_nothing_keeps_the_plain_policy(self):
        base = base_policy()

        assert spa_policy(base, sells=False) == base

    def test_the_settings_are_never_changed(self):
        base = base_policy()
        snapshot = {name: list(sources) for name, sources in base.items()}

        spa_policy(base, sells=True)

        assert base == snapshot


@pytest.mark.django_db
@pytest.mark.usefixtures("spa_manifest")
class TestTheSpaPage:
    def test_the_spa_admits_stripe_with_its_nonce(self, client):
        response = client.get("/dashboard/store/plans", HTTP_HOST=HOST)

        header = directives(response["Content-Security-Policy"])
        assert "https://js.stripe.com" in header["script-src"]
        assert "'strict-dynamic'" in header["script-src"]
        assert any(re.fullmatch(r"'nonce-[^']+'", source) for source in header["script-src"])
        assert header["frame-src"][0] == "'self'"
        assert "https://checkout.stripe.com" in header["frame-src"]
        assert "https://api.stripe.com" in header["connect-src"]

    def test_production_keeps_trusted_types_with_the_page_s_own_policies(self, client, settings):
        settings.SECURE_CSP = base_policy()

        header = directives(client.get("/dashboard/store/plans", HTTP_HOST=HOST)["Content-Security-Policy"])

        assert "'script'" in header["require-trusted-types-for"]
        assert header["trusted-types"] == base_policy()["trusted-types"]
        assert "erplora-stripe-js" not in header["trusted-types"]

    def test_the_account_surface_sells_nothing_and_admits_no_stripe(self, client):
        response = client.get("/dashboard/account?surface=account", HTTP_HOST=HOST)

        assert "stripe.com" not in response["Content-Security-Policy"]

    @pytest.mark.parametrize("path", ["/", "/robots.txt"])
    def test_the_public_web_admits_no_stripe_while_the_panel_does(self, client, path):
        """The public web no longer charges (spec §8.2): its own policy never names Stripe."""
        public = client.get(path, HTTP_HOST=HOST)
        panel = client.get("/launch", HTTP_HOST=HOST)

        assert public.status_code == 200
        assert "stripe.com" not in public["Content-Security-Policy"]
        assert "https://js.stripe.com" in panel["Content-Security-Policy"]

    def test_what_is_not_the_spa_admits_no_stripe(self, client):
        response = client.get("/api/me", HTTP_HOST=HOST)

        assert "stripe.com" not in response.get("Content-Security-Policy", "")
