"""ACCOUNTS-G10: the Content Security Policy of erplora.com, one directive at a time (CLAUDE.md, «Frontend y admin»).

Two policies: the panel's (the SPA and the sign-in, ``settings.SECURE_CSP`` on ``live.csp.base_policy``, read here as
production builds it, in a fresh process) and the public web's (``public.csp.public_policy``, served by
``PublicCSPMiddleware``). Both strict: no ``'unsafe-eval'``, no inline script, nothing from a library CDN, plugins off,
``<base>`` and the forms on our own origin, the Tauri app's hardware bridge (``ipc:`` and ``http://ipc.localhost``) in
``connect-src`` (without it the app loses the hardware with no visible error) and violations reported to
``/csp-report/``. The panel adds what the public web leaves out on purpose (``public/csp.py``): ``'strict-dynamic'``,
Trusted Types and no framing at all.

The assertions read what each directive must and must not hold, never the whole list: an origin a later decision adds
on purpose (Stripe on a page that sells, ``base/csp.py``) does not break them, and a dangerous source still does.
"""

from __future__ import annotations

import json

import pytest
from django.utils.csp import CSP

from config.tests.test_settings import PRODUCTION_ENV, _settings_in_a_fresh_process
from public.csp import public_policy

#: Public CDNs of JavaScript and icons that the old SaaS loaded (OutfitKit, Iconify): never again (PLAN §16.11).
LIBRARY_CDNS = ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com", "api.iconify.design", "esm.sh")
#: Sources that open a directive to any origin, or to every script of one scheme.
WILDCARDS = ("*", "https:", "http:", "data:", "blob:")
ENFORCE_HEADER = "Content-Security-Policy"
REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"


@pytest.fixture(scope="module")
def panel_policy() -> dict[str, list[str]]:
    """``settings.SECURE_CSP`` as a production process builds it (DEBUG off, no Vite)."""
    result = _settings_in_a_fresh_process(PRODUCTION_ENV, "__import__('json').dumps(s.SECURE_CSP)")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def public_production_policy(settings) -> dict[str, list[str]]:
    settings.DEBUG = False
    return public_policy()


def _header_directives(header: str) -> dict[str, list[str]]:
    return {part.split()[0]: part.split()[1:] for part in header.split("; ")}


def _no_library_cdn(policy: dict[str, list[str]]) -> list[str]:
    return [source for sources in policy.values() for source in sources if any(cdn in source for cdn in LIBRARY_CDNS)]


class TestThePanelPolicyInProduction:
    def test_default_src_is_our_own_origin(self, panel_policy):
        assert panel_policy["default-src"] == [CSP.SELF]

    def test_script_src_runs_only_nonced_scripts_and_what_they_load(self, panel_policy):
        script = panel_policy["script-src"]
        assert CSP.SELF in script
        assert CSP.NONCE in script
        assert CSP.STRICT_DYNAMIC in script
        assert CSP.UNSAFE_EVAL not in script
        assert CSP.UNSAFE_INLINE not in script
        assert not set(script) & set(WILDCARDS)

    def test_trusted_types_are_required_with_the_pages_own_policies(self, panel_policy):
        assert panel_policy["require-trusted-types-for"] == ["'script'"]
        assert {"default", "vue"} <= set(panel_policy["trusted-types"])

    def test_connect_src_keeps_the_tauri_bridge(self, panel_policy):
        assert panel_policy["connect-src"][:3] == [CSP.SELF, "ipc:", "http://ipc.localhost"]
        assert not set(panel_policy["connect-src"]) & set(WILDCARDS)

    def test_no_page_of_the_panel_may_be_framed(self, panel_policy):
        assert panel_policy["frame-ancestors"] == [CSP.NONE]

    def test_plugins_are_off_and_base_stays_on_our_origin(self, panel_policy):
        assert panel_policy["object-src"] == [CSP.NONE]
        assert panel_policy["base-uri"] == [CSP.SELF]

    def test_forms_post_to_our_origin_google_and_the_hubs_only(self, panel_policy):
        assert panel_policy["form-action"] == [
            CSP.SELF,
            "https://accounts.google.com",
            "https://*.erplora.com",
            "https://hubs.erplora.com",
        ]

    def test_styles_fonts_and_images_come_from_our_origin(self, panel_policy):
        assert panel_policy["style-src"][0] == CSP.SELF
        assert panel_policy["font-src"] == [CSP.SELF, "data:"]
        assert panel_policy["img-src"][0] == CSP.SELF
        assert "https:" not in panel_policy["img-src"]

    def test_violations_are_reported(self, panel_policy):
        assert panel_policy["report-uri"] == ["/csp-report/"]

    def test_nothing_comes_from_a_library_cdn(self, panel_policy):
        assert _no_library_cdn(panel_policy) == []


class TestThePublicPolicyInProduction:
    def test_default_src_is_our_own_origin(self, public_production_policy):
        assert public_production_policy["default-src"] == [CSP.SELF]

    def test_script_src_runs_only_nonced_scripts(self, public_production_policy):
        script = public_production_policy["script-src"]
        assert script[:2] == [CSP.SELF, CSP.NONCE]
        assert CSP.UNSAFE_EVAL not in script
        assert CSP.UNSAFE_INLINE not in script
        assert not set(script) & set(WILDCARDS)

    def test_connect_src_keeps_the_tauri_bridge(self, public_production_policy):
        assert public_production_policy["connect-src"][:3] == [CSP.SELF, "ipc:", "http://ipc.localhost"]

    def test_only_our_own_origin_may_frame_it(self, public_production_policy):
        assert public_production_policy["frame-ancestors"] == [CSP.SELF]

    def test_plugins_are_off_base_and_forms_stay_on_our_origin(self, public_production_policy):
        assert public_production_policy["object-src"] == [CSP.NONE]
        assert public_production_policy["base-uri"] == [CSP.SELF]
        assert public_production_policy["form-action"] == [CSP.SELF]

    def test_fonts_come_from_our_origin(self, public_production_policy):
        assert public_production_policy["font-src"] == [CSP.SELF, "data:"]

    def test_violations_are_reported(self, public_production_policy):
        assert public_production_policy["report-uri"] == ["/csp-report/"]

    def test_nothing_comes_from_a_library_cdn(self, public_production_policy):
        assert _no_library_cdn(public_production_policy) == []


@pytest.mark.django_db
class TestTheServedPages:
    """Both policies are enforced on the page they belong to, with a fresh nonce in ``script-src``."""

    @pytest.mark.usefixtures("spa_manifest")
    def test_the_panel_enforces_its_policy_with_a_nonce(self, client, settings, panel_policy):
        settings.DEBUG = False
        settings.SECURE_CSP = panel_policy

        response = client.get("/launch")

        assert REPORT_ONLY_HEADER not in response.headers
        script = _header_directives(response.headers[ENFORCE_HEADER])["script-src"]
        assert any(source.startswith("'nonce-") for source in script)
        assert "'strict-dynamic'" in script
        assert "require-trusted-types-for" in response.headers[ENFORCE_HEADER]

    @pytest.mark.usefixtures("spa_manifest")
    def test_the_public_web_enforces_its_policy_with_a_nonce(self, client, settings):
        settings.DEBUG = False

        response = client.get("/", HTTP_HOST="localhost:8001")

        assert response.status_code == 200
        assert REPORT_ONLY_HEADER not in response.headers
        directives = _header_directives(response.headers[ENFORCE_HEADER])
        assert any(source.startswith("'nonce-") for source in directives["script-src"])
        assert "'strict-dynamic'" not in directives["script-src"]
        assert directives["frame-ancestors"] == ["'self'"]
