"""The foundations of the public downloads: presign against the bucket and pick the store.

Port of ``apps/public/tests/test_downloads.py`` (14, origin/develop c5ca8ca), same cases, against
``public.downloads``. The downloads bucket is PRIVATE: the views presign a short-lived GET URL
and redirect to it (nothing world-public). On top of that, ``store_url_for`` is the ONLY switch
between «store» and «our own binary».

What changed (Ioan, 2026-10-13; PLAN-AWS «s3_downloads.tf»): the installers no longer live in
Hetzner's object storage but in a private S3 bucket on AWS, region ``eu-west-1`` (Ireland, the
platform's region since 2026-10-14). The client takes
no static keys: boto3 uses the ECS task's role (or the environment in development); only local
development may point it at another endpoint (``DOWNLOADS_ENDPOINT_URL``).

Who uses these two helpers is ``public.appdist``; its behaviour is tested in ``test_appdist.py``.
"""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest


@pytest.fixture
def aws_environment(monkeypatch, tmp_path):
    """Dummy credentials and no local AWS config: a presigned URL is signed locally, offline."""
    for name in ("AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION", "AWS_REGION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATESTTESTTESTTEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))


#: The setting names ``public.appdist`` calls the helper with, declared once so that each case
#: tests the BEHAVIOUR and does not copy the wiring again.
STORE_SETTINGS = {
    "ms_store_setting": "MICROSOFT_STORE_APP_ID",
    "play_setting": "GOOGLE_PLAY_APP_ID",
    "play_live_setting": "GOOGLE_PLAY_LISTING_LIVE",
}


class TestPresignedDownloadUrl:
    """``presigned_download_url`` signs against the private bucket."""

    def test_presigns_get_object_for_bucket_and_key(self, settings):
        settings.DOWNLOADS_BUCKET = "erplora-downloads"
        settings.DOWNLOAD_URL_TTL = 300
        from public import downloads

        fake_client = MagicMock()
        fake_client.generate_presigned_url.return_value = (
            "https://signed.example/obj?sig=abc"
        )
        with patch.object(downloads, "_s3_client", return_value=fake_client):
            url = downloads.presigned_download_url(
                "downloads/app/latest/erplora-app-setup.exe"
            )

        assert url == "https://signed.example/obj?sig=abc"
        fake_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={
                "Bucket": "erplora-downloads",
                "Key": "downloads/app/latest/erplora-app-setup.exe",
            },
            ExpiresIn=300,
        )

    def test_an_explicit_ttl_wins_over_the_setting(self, settings):
        settings.DOWNLOAD_URL_TTL = 300
        from public import downloads

        fake_client = MagicMock()
        with patch.object(downloads, "_s3_client", return_value=fake_client):
            downloads.presigned_download_url("downloads/app/latest/x", ttl=60)

        assert fake_client.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 60

    def test_the_client_takes_no_static_keys(self, settings):
        """boto3 takes the credentials of the ECS task's role: never a key from the settings."""
        from public import downloads

        with patch.object(downloads.boto3, "client") as client:
            downloads._s3_client()

        kwargs = client.call_args.kwargs
        assert client.call_args.args == ("s3",)
        assert kwargs["region_name"] == "eu-west-1"
        assert "aws_access_key_id" not in kwargs
        assert "aws_secret_access_key" not in kwargs

    def test_a_slow_s3_fails_fast_instead_of_holding_the_request(self, settings):
        """A download waits on S3 inside the request: an S3 (or a local one) that hangs must fail
        within seconds, once, never with botocore's 60 s reads and its retries."""
        from public import downloads

        with patch.object(downloads.boto3, "client") as client:
            downloads._s3_client()

        config = client.call_args.kwargs["config"]
        assert (config.connect_timeout, config.read_timeout) == (2, 3)
        assert config.retries == {"max_attempts": 1}
        assert config.signature_version == "s3v4"

    def test_a_presigned_url_is_on_the_regional_host_of_the_bucket(
        self, settings, aws_environment
    ):
        """Never the legacy global host (`<bucket>.s3.amazonaws.com`): S3 does not serve it for
        regions launched after 2019 and answers a new bucket of an older one, eu-west-1 included,
        with a redirect. It must be the regional host, signed (SigV4) for that region."""
        settings.DOWNLOADS_BUCKET = "erplora-downloads"
        settings.DOWNLOADS_ENDPOINT_URL = ""
        from public import downloads

        url = urlsplit(downloads.presigned_download_url("downloads/app/latest/x.exe"))

        assert url.netloc == "erplora-downloads.s3.eu-west-1.amazonaws.com"
        assert url.path == "/downloads/app/latest/x.exe"
        credential = parse_qs(url.query)["X-Amz-Credential"][0]
        assert credential.split("/")[2:4] == ["eu-west-1", "s3"]

    def test_local_development_may_point_the_client_at_a_local_s3(
        self, settings, aws_environment
    ):
        """A local S3 (MinIO and the like) is addressed by path, on the given endpoint."""
        settings.DOWNLOADS_BUCKET = "erplora-downloads"
        settings.DOWNLOADS_ENDPOINT_URL = "http://localhost:9000"
        from public import downloads

        url = urlsplit(downloads.presigned_download_url("downloads/app/latest/x.exe"))

        assert url.netloc == "localhost:9000"
        assert url.path == "/erplora-downloads/downloads/app/latest/x.exe"


class TestStoreUrlFor:
    """``store_url_for`` — the per-platform switch to the stores (saas#707, ADR-0160).

    Windows → the Web Installer Direct of the single Microsoft Store listing, by its Store ID
    (assigned by Microsoft: without it, the web download is right). Android → the single Google
    Play listing; ``GOOGLE_PLAY_LISTING_LIVE`` says whether it EXISTS, ``GOOGLE_PLAY_APP_ID`` only
    overrides the baked-in package (never a switch to the APK, hub#984). Linux never goes to a
    store.
    """

    def test_windows_uses_ms_store_web_installer_when_configured(self, settings):
        settings.MICROSOFT_STORE_APP_ID = "9NBLGGH4ERPL"
        from public.downloads import store_url_for

        assert (
            store_url_for("windows", **STORE_SETTINGS)
            == "https://get.microsoft.com/installer/download/9NBLGGH4ERPL"
        )

    def test_android_uses_google_play_when_the_listing_is_live(self, settings):
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app"
        from public.downloads import store_url_for

        assert (
            store_url_for("android", **STORE_SETTINGS)
            == "https://play.google.com/store/apps/details?id=com.erplora.app"
        )

    def test_android_has_no_store_while_the_listing_is_not_live(self, settings):
        """saas#1719: the URL of a listing that does not exist is Google's 404, not an answer."""
        settings.GOOGLE_PLAY_LISTING_LIVE = False
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app"
        from public.downloads import store_url_for

        assert store_url_for("android", **STORE_SETTINGS) is None

    def test_windows_returns_none_when_its_setting_is_empty(self, settings):
        settings.MICROSOFT_STORE_APP_ID = ""
        from public.downloads import store_url_for

        assert store_url_for("windows", **STORE_SETTINGS) is None

    def test_android_still_goes_to_play_with_the_package_setting_empty(self, settings):
        """hub#984: an empty package setting resolves to the baked-in package, never to the APK."""
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = ""
        from public.downloads import ANDROID_PLAY_PACKAGE, store_url_for

        assert (
            store_url_for("android", **STORE_SETTINGS)
            == f"https://play.google.com/store/apps/details?id={ANDROID_PLAY_PACKAGE}"
        )
        assert ANDROID_PLAY_PACKAGE == "com.erplora.app"

    def test_linux_never_goes_to_a_store(self, settings):
        settings.MICROSOFT_STORE_APP_ID = "9NBLGGH4ERPL"
        settings.GOOGLE_PLAY_LISTING_LIVE = True
        settings.GOOGLE_PLAY_APP_ID = "com.erplora.app"
        from public.downloads import store_url_for

        assert store_url_for("linux", **STORE_SETTINGS) is None


class TestStoreSettingsContract:
    """The store settings (ADR-0160): one listing per store, no legacy aliases."""

    def test_google_play_app_id_exists_with_empty_default(self):
        from django.conf import settings as django_settings

        assert getattr(django_settings, "GOOGLE_PLAY_APP_ID", None) == ""

    def test_google_play_listing_is_declared_live_by_default(self):
        """The listing is published since 2026-10-01: «live» is the truthful default."""
        from django.conf import settings as django_settings

        assert getattr(django_settings, "GOOGLE_PLAY_LISTING_LIVE", None) is True

    def test_google_play_bridge_id_is_gone(self):
        from django.conf import settings as django_settings

        assert not hasattr(django_settings, "GOOGLE_PLAY_BRIDGE_ID")

    def test_microsoft_store_app_id_exists_with_empty_default(self):
        from django.conf import settings as django_settings

        assert getattr(django_settings, "MICROSOFT_STORE_APP_ID", None) == ""

    def test_the_downloads_bucket_is_on_aws_in_ireland_by_default(self):
        from django.conf import settings as django_settings

        assert django_settings.DOWNLOADS_REGION == "eu-west-1"
        assert django_settings.DOWNLOADS_ENDPOINT_URL == ""

    def test_the_hetzner_object_storage_settings_are_gone(self):
        from django.conf import settings as django_settings

        assert [
            name for name in dir(django_settings) if name.startswith("HETZNER_")
        ] == []

    def test_microsoft_store_bridge_id_is_gone(self):
        from django.conf import settings as django_settings

        assert not hasattr(django_settings, "MICROSOFT_STORE_BRIDGE_ID")

    def test_settings_that_are_missing_entirely_are_treated_as_empty(self, settings):
        """``store_url_for`` reads by name; a deploy without the variable cannot break the download."""
        del settings.MICROSOFT_STORE_APP_ID
        from public.downloads import store_url_for

        assert store_url_for("windows", **STORE_SETTINGS) is None

    def test_a_missing_play_live_setting_means_the_listing_is_not_live(self, settings):
        """The safe failure is «no listing»: the page, right in both worlds."""
        del settings.GOOGLE_PLAY_LISTING_LIVE
        from public.downloads import store_url_for

        assert store_url_for("android", **STORE_SETTINGS) is None
