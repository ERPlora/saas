"""The installable app ``com.erplora.app``: which version is the latest, where it is downloaded,
its public page ``/app/`` and the «ways to try ERPlora» page ``/download/`` (public/appdist.py).

Port of, from origin/develop c5ca8ca:

* ``apps/public/tests/test_app_distribution.py`` (25): ``GET /api/v1/app/release/`` and
  ``/app/download/<platform>/``. The release is now a ninja route bound to the query
  ``public.app.release`` (PLAN-SAAS §6); the bucket read and its cache stay in ``public.appdist``;
* ``apps/public/tests/test_installable_app_page.py`` (20) without the ``/bridge/`` cases: the Bridge
  and its 301 tombstones are gone (spec §8.3), ``/bridge/`` is a 404 now (one case below fixes it).
  «The home points to the app page» asked the landing, which comes with L7: the same promise is
  asked of the footer, which every public page carries;
* the ``/download/`` cases of ``apps/public/landing/tests/test_views.py`` (``TestDownloadsView``),
  without ``landing:app_download`` (a name that never existed here).

The order of gravity is the old one: never invent a version (``null``, never a number); the
question carries no credential; the 302 decides the channel; Android never hands out the APK.
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.urls import reverse
from hubs.models import Plan

pytestmark = pytest.mark.django_db

RELEASE_URL = "/api/v1/app/release/"
ROOT = Path(settings.BASE_DIR)
#: How the dead product was linked: its URL names and its address.
_DEAD_BRIDGE_LINK = re.compile(r"""bridge:(?:index|download)|href=["']/bridge/""")


def _manifest_body(payload: bytes) -> MagicMock:
    """A boto3 client whose ``get_object`` returns ``payload``."""
    body = MagicMock()
    body.read.return_value = payload
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    return client


@pytest.fixture
def appdist():
    from public import appdist as module

    module.published_release.cache_clear()
    yield module
    module.published_release.cache_clear()


def download_url(platform: str) -> str:
    return reverse("public:app_download", args=[platform])


# --- GET /api/v1/app/release/ (TestPublishedRelease) ---------------------------------------------


class TestPublishedRelease:
    def test_reports_the_version_the_release_published(self, client, appdist):
        with patch.object(
            appdist,
            "_s3_client",
            return_value=_manifest_body(
                b'{"version": "1.4.0", "published_at": "2026-08-08T10:00:00Z"}'
            ),
        ):
            response = client.get(RELEASE_URL)

        assert response.status_code == 200
        assert json.loads(response.content) == {"version": "1.4.0"}

    def test_asks_the_bucket_for_the_key_the_release_writes(self, client, appdist):
        """A contract with `.github/workflows/tauri-release.yml` of the hub repo."""
        fake = _manifest_body(b'{"version": "1.4.0"}')
        with patch.object(appdist, "_s3_client", return_value=fake):
            client.get(RELEASE_URL)

        assert (
            fake.get_object.call_args.kwargs["Key"]
            == "downloads/app/latest/latest.json"
        )

    def test_says_it_does_not_know_when_the_manifest_is_missing(self, client, appdist):
        client_mock = MagicMock()
        client_mock.get_object.side_effect = Exception("NoSuchKey")
        with patch.object(appdist, "_s3_client", return_value=client_mock):
            response = client.get(RELEASE_URL)

        assert response.status_code == 200
        assert json.loads(response.content)["version"] is None

    def test_says_it_does_not_know_when_the_manifest_is_not_json(self, client, appdist):
        with patch.object(
            appdist, "_s3_client", return_value=_manifest_body(b"<html>nope</html>")
        ):
            response = client.get(RELEASE_URL)

        assert json.loads(response.content)["version"] is None

    def test_says_it_does_not_know_when_the_version_is_not_a_string(
        self, client, appdist
    ):
        with patch.object(
            appdist, "_s3_client", return_value=_manifest_body(b'{"version": 140}')
        ):
            response = client.get(RELEASE_URL)

        assert json.loads(response.content)["version"] is None

    def test_says_it_does_not_know_when_the_version_is_blank(self, client, appdist):
        with patch.object(
            appdist, "_s3_client", return_value=_manifest_body(b'{"version": "  "}')
        ):
            response = client.get(RELEASE_URL)

        assert json.loads(response.content)["version"] is None

    def test_answers_without_any_credential(self, client, appdist):
        """Anonymous, no `X-Hub-Token`, no `Authorization`: the Hub's runtime asks so."""
        with patch.object(
            appdist, "_s3_client", return_value=_manifest_body(b'{"version": "1.4.0"}')
        ):
            response = client.get(RELEASE_URL)

        assert response.status_code == 200

    def test_reads_the_bucket_once_for_a_whole_fleet(self, client, appdist):
        """Every till asks every 6 h for something that changes once per release."""
        fake = _manifest_body(b'{"version": "1.4.0"}')
        with patch.object(appdist, "_s3_client", return_value=fake):
            client.get(RELEASE_URL)
            client.get(RELEASE_URL)

        assert fake.get_object.call_count == 1

    def test_a_new_time_bucket_reads_the_bucket_again(self, appdist):
        """The cache expires by time bucket: a new release is seen without a restart."""
        fake = _manifest_body(b'{"version": "1.4.0"}')
        with patch.object(appdist, "_s3_client", return_value=fake):
            appdist.published_release(1)
            appdist.published_release(2)

        assert fake.get_object.call_count == 2


# --- GET /app/download/<platform>/ (TestAppDownloadView) -------------------------------------------


class TestAppDownloadView:
    def test_serves_the_app_installer(self, client):
        with patch(
            "public.appdist.presigned_download_url",
            return_value="https://signed.example/app?sig=x",
        ) as presign:
            response = client.get(download_url("windows"))

        assert response.status_code == 302
        assert response["Location"] == "https://signed.example/app?sig=x"
        assert presign.call_args.args[0] == "downloads/app/latest/erplora-app-setup.exe"

    @pytest.mark.parametrize(
        ("platform", "filename"),
        [("windows", "erplora-app-setup.exe"), ("linux", "erplora-app.AppImage")],
    )
    def test_each_platform_gets_its_own_binary(self, client, platform, filename):
        with patch(
            "public.appdist.presigned_download_url",
            return_value="https://signed.example/x",
        ) as presign:
            client.get(download_url(platform))

        assert presign.call_args.args[0].endswith(filename)

    def test_never_hands_out_a_versioned_address(self, client):
        """Point 1 of hub#400: `latest/`, so a cached link keeps delivering the last build."""
        with patch(
            "public.appdist.presigned_download_url",
            return_value="https://signed.example/x",
        ) as presign:
            client.get(download_url("linux"))

        assert "/v" not in presign.call_args.args[0].removeprefix("downloads/app/")

    def test_macos_is_not_served_because_nothing_publishes_one(self, client):
        assert client.get(download_url("macos")).status_code == 404

    def test_unknown_platform_404(self, client):
        assert client.get(download_url("solaris")).status_code == 404

    def test_windows_goes_to_the_microsoft_store_once_the_listing_is_live(
        self, client, settings
    ):
        settings.MICROSOFT_STORE_APP_ID = "9NBLGGH4ABCD"
        response = client.get(download_url("windows"))

        assert response.status_code == 302
        assert (
            response["Location"]
            == "https://get.microsoft.com/installer/download/9NBLGGH4ABCD"
        )

    def test_android_goes_to_play_once_the_listing_is_live(self, client, settings):
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app"
        response = client.get(download_url("android"))

        assert response.status_code == 302
        assert (
            response["Location"]
            == "https://play.google.com/store/apps/details?id=com.erplora.app"
        )

    def test_linux_never_goes_to_a_store(self, client, settings):
        settings.MICROSOFT_STORE_APP_ID = "9NBLGGH4ABCD"
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app"
        with patch(
            "public.appdist.presigned_download_url",
            return_value="https://signed.example/x",
        ):
            response = client.get(download_url("linux"))

        assert response["Location"] == "https://signed.example/x"

    def test_android_never_hands_out_an_apk_even_with_the_setting_empty(
        self, client, settings
    ):
        """The heart of hub#984: the package is baked into the AAB, not a deploy switch."""
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = ""
        with patch("public.appdist.presigned_download_url") as presign:
            response = client.get(download_url("android"))

        assert response.status_code == 302
        assert (
            response["Location"]
            == "https://play.google.com/store/apps/details?id=com.erplora.app"
        )
        presign.assert_not_called()

    def test_android_setting_still_overrides_the_baked_in_package(
        self, client, settings
    ):
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app.staging"
        response = client.get(download_url("android"))

        assert (
            response["Location"]
            == "https://play.google.com/store/apps/details?id=com.erplora.app.staging"
        )

    def test_android_goes_to_play_without_any_env_now_that_the_listing_is_published(
        self, client
    ):
        assert settings.GOOGLE_PLAY_LISTING_LIVE is True
        response = client.get(download_url("android"))

        assert response.status_code == 302
        assert (
            response["Location"]
            == "https://play.google.com/store/apps/details?id=com.erplora.app"
        )

    def test_the_download_is_only_answered_to_safe_methods(self, client):
        assert client.post(download_url("linux")).status_code == 405


class TestAndroidPageWhileThePlayListingIsNotLive:
    """`/app/download/android/` serves a page of ours while the Play listing does not exist (saas#1719)."""

    @pytest.fixture(autouse=True)
    def _listing_switched_off(self, settings):
        settings.GOOGLE_PLAY_LISTING_LIVE = False

    def test_serves_our_own_page_instead_of_inheriting_the_play_404(self, client):
        response = client.get(download_url("android"))

        assert response.status_code == 200
        assert "public/appdist/android.html" in [t.name for t in response.templates]

    def test_the_page_never_offers_the_apk(self, client, settings):
        settings.GOOGLE_PLAY_APP_ID = ""
        with patch("public.appdist.presigned_download_url") as presign:
            response = client.get(download_url("android"))

        presign.assert_not_called()
        # The positive control first: an EMPTY response (the old 302) would pass the `not in`s.
        assert response.status_code == 200
        html = response.content.decode()
        assert "Google Play" in html
        assert ".apk" not in html
        assert "your-objectstorage" not in html
        assert "amazonaws.com" not in html

    def test_the_page_offers_the_platforms_that_do_have_a_build(self, client):
        html = client.get(download_url("android")).content.decode()

        assert download_url("windows") in html
        assert download_url("linux") in html
        assert reverse("public:app") in html

    def test_the_page_offers_to_create_a_hub_at_the_sign_in(self, client):
        html = client.get(download_url("android")).content.decode()

        assert 'href="/launch"' in html
        assert "/accounts/login/" not in html

    def test_the_page_is_indexable(self, client):
        response = client.get(download_url("android"))
        html = response.content.decode()

        assert response.status_code == 200
        assert "<title>" in html
        assert "noindex" not in html
        assert 'rel="canonical" href="https://testserver/app/download/android/"' in html

    def test_the_page_is_translated_into_spanish(self, client):
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        html = client.get(download_url("android")).content.decode()

        assert "Muy pronto en Google Play" in html

    def test_it_flips_to_play_with_a_setting_the_day_the_listing_goes_live(
        self, client, settings
    ):
        settings.GOOGLE_PLAY_LISTING_LIVE = True

        response = client.get(download_url("android"))

        assert response.status_code == 302
        assert (
            response["Location"]
            == "https://play.google.com/store/apps/details?id=com.erplora.app"
        )

    def test_the_other_platforms_are_untouched(self, client):
        with patch(
            "public.appdist.presigned_download_url",
            return_value="https://signed.example/x",
        ):
            for platform in ("windows", "linux"):
                assert client.get(download_url(platform)).status_code == 302
        assert client.get(download_url("macos")).status_code == 404
        assert client.get(download_url("solaris")).status_code == 404


# --- /app/ (test_installable_app_page.py) -----------------------------------------------------


class TestInstallableAppPage:
    def test_page_is_served(self, client):
        response = client.get("/app/")

        assert response.status_code == 200
        assert reverse("public:app") == "/app/"
        assert "<title>The ERPlora app · ERPlora</title>" in response.content.decode()

    @pytest.mark.parametrize("platform", ["windows", "linux", "android"])
    def test_every_download_button_resolves_to_the_download(self, client, platform):
        assert download_url(platform) in client.get("/app/").content.decode()

    def test_page_never_links_back_to_the_dead_bridge(self, client):
        assert "/bridge/" not in client.get("/app/").content.decode()

    def test_page_shows_store_labels_when_the_listings_are_live(self, client, settings):
        settings.MICROSOFT_STORE_APP_ID = "9NBLGGH4ERPL"
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app"

        html = client.get("/app/").content.decode()

        assert "Get it from Microsoft Store" in html
        assert "Get it on Google Play" in html

    def test_android_button_says_get_it_on_play_with_no_env(self, client):
        html = client.get("/app/").content.decode()
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        html_es = client.get("/app/").content.decode()

        assert "Get it on Google Play" in html
        assert "Coming to Google Play" not in html
        assert "Consíguela en Google Play" in html_es

    def test_android_button_says_coming_while_the_play_listing_is_not_live(
        self, client, settings
    ):
        settings.GOOGLE_PLAY_LISTING_LIVE = False
        html = client.get("/app/").content.decode()

        assert "Coming to Google Play" in html
        assert "Get it on Google Play" not in html

    def test_windows_shows_a_plain_download_label_without_its_store_listing(
        self, client, settings
    ):
        settings.MICROSOFT_STORE_APP_ID = ""

        html = client.get("/app/").content.decode()

        assert "Microsoft Store" not in html
        assert "Download the app" in html

    def test_android_always_reads_as_google_play_never_as_a_download(
        self, client, settings
    ):
        settings.GOOGLE_PLAY_APP_ID = ""

        assert "Google Play" in client.get("/app/").content.decode()

    def test_page_states_the_limits_instead_of_promising_them(self, client):
        html = client.get("/app/").content.decode()

        assert "USB and Bluetooth printer transport are not supported." in html
        assert download_url("macos") not in html
        assert "never updates itself" in html
        assert "works offline" not in html.lower()
        assert "offline-first" not in html.lower()

    def test_page_offers_to_create_a_hub_first(self, client):
        html = client.get("/app/").content.decode()

        assert "You need a hub before you need the app." in html
        assert 'href="/launch"' in html
        assert "/accounts/login/" not in html


class TestTheAppPageIsTranslated:
    def test_spanish_visitors_get_spanish(self, client):
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        html = client.get("/app/").content.decode()

        assert "Tu hub y tu hardware, en una sola app." in html
        assert "Hardware compatible" in html
        assert "Impresora de tiques" in html
        assert (
            "El transporte de impresora por USB y por Bluetooth no está soportado."
            in html
        )


# --- /download/ (TestDownloadsView of landing/tests/test_views.py) -------------------------------


class TestWaysToTryPage:
    def test_download_renders_the_two_free_ways_to_try(self, client):
        response = client.get("/download/")

        assert response.status_code == 200
        assert reverse("public:downloads") == "/download/"
        html = response.content.decode()
        # Path A: create a free cloud hub, through the sign-in (which also signs up).
        assert 'href="/launch"' in html
        assert "/accounts/login/" not in html
        # Path B: the app for the counter hardware, per platform, and its page.
        for platform in ("windows", "linux", "android"):
            assert download_url(platform) in html
        assert reverse("public:app") in html
        assert "/bridge/" not in html

    def test_download_does_not_link_the_old_demo_host(self, client):
        assert "demo.erplora.com" not in client.get("/download/").content.decode()

    def test_download_does_not_promise_premium_apps_on_the_free_plan(self, client):
        """Premium apps come with the paid plans (spec decision 17): the free hub has the free ones."""
        html = client.get("/download/").content.decode()

        assert "All modules included" not in html
        assert "All free apps included, VeriFactu ready" in html

    def test_download_in_spanish(self, client):
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
        html = client.get("/download/").content.decode()

        assert "Dos formas gratuitas de probar ERPlora." in html


# --- PUBLIC-G28: the free hub's limits are the Free plan's, never typed ----------------------------


def free_hub_card(html: str, a: str = "Option A", b: str = "Option B") -> str:
    """Option A of /download/: the card of the free cloud hub."""
    start = html.index(a)
    return html[start : html.index(b, start)]


class TestTheFreeHubStatesTheFreePlan:
    """PUBLIC-G28 (FIX of APP-PUBLIC-1): «1 device, 3 local users» was typed in the template."""

    def test_it_states_the_devices_and_users_of_the_free_plan(self, client):
        Plan.objects.filter(slug="free").update(max_devices=2, max_users=5)

        card = free_hub_card(client.get("/download/").content.decode())

        assert "2 devices · 5 users" in card
        assert "3 local users" not in card

    def test_an_unlimited_free_plan_says_so(self, client):
        Plan.objects.filter(slug="free").update(max_devices=0, max_users=0)

        card = free_hub_card(client.get("/download/").content.decode())

        assert "Unlimited devices · Unlimited users" in card

    def test_in_spanish_it_reads_the_same_plan(self, client):
        Plan.objects.filter(slug="free").update(max_devices=1, max_users=4)
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"

        card = free_hub_card(client.get("/download/").content.decode(), "Opción A", "Opción B")

        assert "1 dispositivo · 4 usuarios" in card

    def test_without_a_free_plan_on_sale_no_limit_is_invented(self, client):
        Plan.objects.filter(price_monthly=0).delete()

        card = free_hub_card(client.get("/download/").content.decode())

        assert "device" not in card
        assert "users" not in card


# --- Everything points at the app, nothing at the Bridge ----------------------------------------


class TestPublicPagesSendPeopleToTheApp:
    def test_the_footer_points_to_the_app_page_and_the_downloads(self, client):
        """On every public page (the footer is one partial): the home's promise until L7."""
        html = client.get("/features/").content.decode()
        footer = html[html.index('<footer class="ep-footer"') :]

        assert f'href="{reverse("public:app")}"' in footer
        assert f'href="{reverse("public:downloads")}"' in footer
        assert "/bridge/" not in footer

    def test_the_bridge_is_gone_not_redirected(self, client):
        """Spec §8.3: no tombstone, a 404 of the public web."""
        assert client.get("/bridge/").status_code == 404
        assert client.get("/bridge/download/windows/").status_code == 404


class TestNoSurfaceLinksToTheDeadBridge:
    def test_no_template_links_to_the_bridge_download_or_page(self):
        offenders = [
            str(path.relative_to(ROOT))
            for folder in (ROOT / "public" / "templates", ROOT / "templates")
            for path in folder.rglob("*.html")
            if _DEAD_BRIDGE_LINK.search(path.read_text(encoding="utf-8"))
        ]

        assert offenders == []

    def test_there_is_no_bridge_template(self):
        assert not list((ROOT / "public" / "templates").rglob("*bridge*"))


class TestSitemapPublishesTheAppPage:
    def test_the_static_sitemap_offers_the_app_page(self):
        from public.sitemaps import StaticPagesSitemap

        assert ("public:app", 0.7) in StaticPagesSitemap.pages
        assert not any("bridge" in name for name, _ in StaticPagesSitemap.pages)

    def test_rendered_sitemap_indexes_the_app_page_only(self, client):
        xml = client.get("/sitemap.xml").content.decode()

        assert "/app/</loc>" in xml
        assert "/bridge/" not in xml


def test_llms_txt_points_at_the_counter_app(client):
    body = client.get("/llms.txt").content.decode()

    assert (
        "- [Counter app](https://testserver/app/): the installable app that drives "
        "printers and cash drawer." in body
    )
