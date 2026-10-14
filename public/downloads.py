"""Presigned downloads from the private S3 bucket, and the switch to the app stores.

Port of ``apps/public/downloads.py`` (origin/develop c5ca8ca). The hub's CI
(``tauri-release.yml``) uploads the installers of the app to ``downloads/app/latest/`` of a PRIVATE
S3 bucket on AWS (``DOWNLOADS_BUCKET`` in ``DOWNLOADS_REGION``, Ireland; PLAN-AWS «s3_downloads.tf»;
before, Hetzner's object storage), so the public download asks for a short-lived presigned GET URL
instead of redirecting to a world-public object. The client takes no static keys: boto3 uses the
ECS task's role, or the environment in development, where ``DOWNLOADS_ENDPOINT_URL`` may point it
at a local S3. ``store_url_for`` is the ONLY switch between «store» and «our own binary»;
``public.appdist`` uses both.
"""

import boto3
from botocore.config import Config
from django.conf import settings

#: The ``applicationId`` of the installable app. NOT deploy configuration: it is baked into the AAB
#: the CI uploads and it is the same string that names the Play listing, so it is known at code
#: time. That is why Android's door does not ask an environment variable (hub#984): when it did, a
#: deploy without the variable handed out the APK outside Play, silently.
ANDROID_PLAY_PACKAGE = "com.erplora.app"


def _s3_client():
    """S3 in the downloads region; AWS itself unless local development sets another endpoint.

    On AWS, the bucket's REGIONAL host (``<bucket>.s3.<region>.amazonaws.com``), signed with
    SigV4: boto3's default for a presigned URL may be the legacy global host, which S3 does not
    serve for regions launched after 2019 and answers with a redirect for a new bucket of an older
    one such as eu-west-1. A local S3 is addressed by path.

    The request waits on it: a hanging S3 fails within seconds and once, instead of botocore's
    60 s reads and its retries.
    """
    endpoint = settings.DOWNLOADS_ENDPOINT_URL or None
    return boto3.client(
        "s3",
        region_name=settings.DOWNLOADS_REGION,
        endpoint_url=endpoint,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if endpoint else "virtual"},
            connect_timeout=2,
            read_timeout=3,
            retries={"max_attempts": 1},
        ),
    )


def store_url_for(
    platform: str, *, ms_store_setting: str, play_setting: str, play_live_setting: str
) -> str | None:
    """The store URL for ``platform``, or ``None`` when there is no store to offer (saas#707).

    * ``windows`` → the Web Installer Direct of the single «ERPlora» listing of Microsoft Store
      (ADR-0160), by its Store ID. Microsoft assigns that ID and it cannot be derived, so here the
      setting is a legitimate switch: without it, the web download is the right channel.
    * ``android`` → the single Google Play listing (Android client = Play ONLY). Two settings that
      do different things: ``play_live_setting`` says whether the listing EXISTS (off → ``None``,
      and the view serves a page of ours, never the APK; saas#1719); ``play_setting`` only
      overrides the ``applicationId`` (empty means ``ANDROID_PLAY_PACKAGE``, never «hand out the
      APK»; hub#984).
    * any other platform (linux, macos…) → ``None``.

    ``None`` does NOT mean «serve the binary»: it means «no store». Which platforms fall back to
    the presigned binary is ``public.appdist``'s list, where Android is not and will not be.
    """
    if platform == "windows":
        store_id = getattr(settings, ms_store_setting, "")
        if store_id:
            return f"https://get.microsoft.com/installer/download/{store_id}"
    elif platform == "android":
        if not getattr(settings, play_live_setting, False):
            return None
        package = getattr(settings, play_setting, "") or ANDROID_PLAY_PACKAGE
        return f"https://play.google.com/store/apps/details?id={package}"
    return None


def presigned_download_url(key: str, *, ttl: int | None = None) -> str:
    """A presigned GET URL for ``key`` in the downloads bucket (TTL from the settings by default)."""
    bucket = getattr(settings, "DOWNLOADS_BUCKET", "erplora-saas")
    if ttl is None:
        ttl = getattr(settings, "DOWNLOAD_URL_TTL", 300)
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=ttl,
    )
