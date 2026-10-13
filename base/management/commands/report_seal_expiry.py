"""``python manage.py report_seal_expiry``: daily in ``saas-cron`` (07:00 UTC, aws-next ``scheduler.tf``).

Publishes in CloudWatch ``ERPlora/Fiscal`` the metric ``SealDaysToExpiry``: the days until the fiscal
seal of the slot that expires first, rounded down (expired = negative), without dimensions. The
``seal_expiry`` alarm (``alarms.tf``) takes the daily minimum and fires under 30 days. The slots are
the two .p12 of ``FISCAL_SEAL_{CURRENT,NEXT}_{P12_BASE64,PASSWORD}`` (empty = an empty slot).

- Both slots empty: nothing is published and AWS is never called.
- A slot that cannot be read (base64, password, no certificate) or a publication that fails ends the
  run with an error (exit ≠ 0: the ``task_failed`` rule warns) that names the slot, never what it
  holds; nothing is published, not even the days of the other slot.
- Idempotent (no state) and under a transaction advisory lock: while another run holds it, this one
  returns at once without publishing.
"""

import base64
import binascii
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import pkcs12
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

NAMESPACE = "ERPlora/Fiscal"
METRIC = "SealDaysToExpiry"
LOCK = "SELECT pg_try_advisory_xact_lock(hashtext('erplora.saas.report_seal_expiry'))"

#: Each slot and the settings of its .p12 (base64) and its password.
SLOTS = {
    "current": ("FISCAL_SEAL_CURRENT_P12_BASE64", "FISCAL_SEAL_CURRENT_PASSWORD"),
    "next": ("FISCAL_SEAL_NEXT_P12_BASE64", "FISCAL_SEAL_NEXT_PASSWORD"),
}


class Command(BaseCommand):
    help = "Publish the days until the fiscal seal expires (CloudWatch ERPlora/Fiscal SealDaysToExpiry)."

    def handle(self, *args, **options):
        filled = {
            slot: (getattr(settings, data), getattr(settings, password))
            for slot, (data, password) in SLOTS.items()
            if getattr(settings, data)
        }
        if not filled:
            self.stdout.write(
                "report_seal_expiry: both seal slots are empty, nothing published."
            )
            return
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(LOCK)
                mine = cursor.fetchone()[0]
            if not mine:
                self.stdout.write(
                    "report_seal_expiry: already running, nothing published."
                )
                return
            now = timezone.now()
            days = {
                slot: days_left(slot, data, password, now)
                for slot, (data, password) in filled.items()
            }
            first = min(days.values())
            publish(first)
        slots = ", ".join(f"{slot}={left}" for slot, left in days.items())
        self.stdout.write(f"report_seal_expiry: {METRIC}={first} ({slots}).")


def days_left(slot: str, data: str, password: str, now: datetime) -> int:
    """Whole days from ``now`` until the certificate of ``slot`` expires (negative once expired).

    Every error names the slot only: neither the .p12 nor its password reaches a message or a
    traceback (``from None``)."""
    try:
        raw = base64.b64decode("".join(data.split()), validate=True)
    except binascii.Error, ValueError:
        raise CommandError(
            f"report_seal_expiry: the {slot} seal slot is not valid base64."
        ) from None
    try:
        _key, certificate, _chain = pkcs12.load_key_and_certificates(
            raw, password.encode() or None
        )
    except ValueError, TypeError, UnsupportedAlgorithm:
        raise CommandError(
            f"report_seal_expiry: the {slot} seal slot is not a .p12 that its password opens."
        ) from None
    if certificate is None:
        raise CommandError(
            f"report_seal_expiry: the {slot} seal slot holds no certificate."
        )
    return (certificate.not_valid_after_utc - now).days


def publish(days: int) -> None:
    """``SealDaysToExpiry`` = ``days`` in the task's region, signed by the task role."""
    try:
        cloudwatch = boto3.client("cloudwatch", region_name=settings.AWS_REGION)
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[{"MetricName": METRIC, "Value": days, "Unit": "Count"}],
        )
    except (BotoCoreError, ClientError) as exc:
        raise CommandError(
            f"report_seal_expiry: could not publish {METRIC} ({exc})."
        ) from exc
