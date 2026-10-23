"""Push the public sitemap URLs to IndexNow. Safe to run repeatedly (it is a ping).

Only from prod: outside it (``pre.erplora.com``, plan 2026-10-14-entorno-pre) nothing is announced to a
search engine, and asking for it is an error, not a quiet no-op.

It runs daily in a scheduled ECS task whose alarm (aws ``task_failed``) only sees the exit code, so a
submission IndexNow rejects or never answers is a failed exit too (PUBLIC-F14); no key is not."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from public import indexnow


class Command(BaseCommand):
    help = "Submit the public sitemap URLs to IndexNow (Bing, Yandex). No-op without INDEXNOW_KEY."

    def add_arguments(self, parser):
        parser.add_argument(
            "--host",
            default=None,
            help="Public host to submit for (default: PUBLIC_HOST).",
        )

    def handle(self, *args, **options):
        if settings.ERPLORA_ENVIRONMENT != "prod":
            raise CommandError(
                f"IndexNow only runs in prod, not in {settings.ERPLORA_ENVIRONMENT}: nothing submitted"
            )
        host = options["host"] or settings.PUBLIC_HOST
        try:
            count = indexnow.submit_sitemap_urls(host=host)
        except indexnow.SubmissionFailed as error:
            raise CommandError(
                f"IndexNow: nothing submitted for {host}: {error}"
            ) from None
        if count:
            self.stdout.write(
                self.style.SUCCESS(f"IndexNow: {count} URLs submitted for {host}")
            )
        else:
            # Not an error exit: no key is a legitimate state (development), and the reason is in
            # the log. But it must never look like success.
            self.stdout.write(
                self.style.WARNING(
                    f"IndexNow: nothing submitted for {host}, see the log"
                )
            )
