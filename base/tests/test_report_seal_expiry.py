"""``manage.py report_seal_expiry`` (``saas-cron``, 07:00 UTC; aws README, «Comandos ``manage.py``»).

For each slot of the fiscal seal that is not empty (``FISCAL_SEAL_{CURRENT,NEXT}_*``) it reads the
certificate of the .p12 and publishes, in ``ERPlora/Fiscal``, ``SealDaysToExpiry`` = the days until
the first one expires, rounded down (expired = negative), without dimensions: the ``seal_expiry``
alarm of ``alarms.tf`` takes the daily minimum and fires under 30. Both slots empty: nothing is
published and AWS is never called. An unreadable slot fails the run (``task_failed`` warns) naming
the slot, never its content, and nothing is published. Idempotent, under an advisory lock.

The .p12 files are generated here with ``cryptography``; CloudWatch is a botocore ``Stubber`` that
demands the exact call.
"""

import base64
import logging
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import boto3
import pytest
from botocore.stub import Stubber
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.core.management import CommandError, call_command
from django.utils import timezone

pytestmark = pytest.mark.django_db

LOCK_KEY = "hashtext('erplora.saas.report_seal_expiry')"
SLOTS = (
    "FISCAL_SEAL_CURRENT_P12_BASE64",
    "FISCAL_SEAL_CURRENT_PASSWORD",
    "FISCAL_SEAL_NEXT_P12_BASE64",
    "FISCAL_SEAL_NEXT_PASSWORD",
)
# Half a day past the whole number, so the floor is the same whenever the test runs.
HALF_DAY = timedelta(hours=12)


def seal(expires_in: timedelta, password: str = "", certificate: bool = True) -> str:
    """A base64 .p12 with a self-signed certificate that expires ``expires_in`` from now."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ERPLORA SL")])
    now = timezone.now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=400))
        .not_valid_after(now + expires_in)
        .sign(key, hashes.SHA256())
    )
    encryption = (
        serialization.BestAvailableEncryption(password.encode())
        if password
        else serialization.NoEncryption()
    )
    data = pkcs12.serialize_key_and_certificates(
        b"seal", key, cert if certificate else None, None, encryption
    )
    return base64.b64encode(data).decode()


def published(days: int) -> dict:
    """The exact ``put_metric_data`` call for ``days``."""
    return {
        "Namespace": "ERPlora/Fiscal",
        "MetricData": [
            {"MetricName": "SealDaysToExpiry", "Value": days, "Unit": "Count"}
        ],
    }


@pytest.fixture(autouse=True)
def empty_slots(settings):
    """Both slots empty and the platform's region, whatever saas-next/.env says."""
    for name in SLOTS:
        setattr(settings, name, "")
    settings.AWS_REGION = "eu-south-2"
    return settings


@pytest.fixture
def cloudwatch(monkeypatch):
    """``boto3.client`` hands the command a stubbed CloudWatch client and records each creation."""
    client = boto3.client(
        "cloudwatch",
        region_name="eu-south-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    created = []

    def factory(service_name, **kwargs):
        created.append((service_name, kwargs))
        return client

    monkeypatch.setattr(boto3, "client", factory)
    with Stubber(client) as stubber:
        yield SimpleNamespace(stubber=stubber, created=created)


def run() -> str:
    out = StringIO()
    call_command("report_seal_expiry", stdout=out)
    return out.getvalue()


def test_the_current_slot_alone_publishes_its_days(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(
        timedelta(days=40) + HALF_DAY, password="s3cret"
    )
    empty_slots.FISCAL_SEAL_CURRENT_PASSWORD = "s3cret"
    cloudwatch.stubber.add_response("put_metric_data", {}, published(40))

    output = run()

    cloudwatch.stubber.assert_no_pending_responses()
    assert cloudwatch.created == [("cloudwatch", {"region_name": "eu-south-2"})]
    assert "SealDaysToExpiry=40" in output


def test_with_both_slots_the_first_to_expire_is_published(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(
        timedelta(days=20) + HALF_DAY, password="current"
    )
    empty_slots.FISCAL_SEAL_CURRENT_PASSWORD = "current"
    # A slot without a password is a .p12 without one.
    empty_slots.FISCAL_SEAL_NEXT_P12_BASE64 = seal(timedelta(days=380) + HALF_DAY)
    cloudwatch.stubber.add_response("put_metric_data", {}, published(20))

    run()

    cloudwatch.stubber.assert_no_pending_responses()


def test_an_expired_seal_publishes_negative_days(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_NEXT_P12_BASE64 = seal(-(timedelta(days=2) + HALF_DAY))
    cloudwatch.stubber.add_response("put_metric_data", {}, published(-3))

    run()

    cloudwatch.stubber.assert_no_pending_responses()


def test_both_slots_empty_publish_nothing_and_never_call_aws(cloudwatch, caplog):
    with caplog.at_level(logging.INFO):
        output = run()

    assert cloudwatch.created == []
    assert "nothing published" in output


def test_the_region_is_the_tasks(empty_slots, cloudwatch):
    empty_slots.AWS_REGION = "eu-west-3"
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(timedelta(days=90) + HALF_DAY)
    cloudwatch.stubber.add_response("put_metric_data", {}, published(90))

    run()

    assert cloudwatch.created == [("cloudwatch", {"region_name": "eu-west-3"})]


def test_two_runs_make_the_same_call(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(timedelta(days=60) + HALF_DAY)
    cloudwatch.stubber.add_response("put_metric_data", {}, published(60))
    cloudwatch.stubber.add_response("put_metric_data", {}, published(60))

    run()
    run()

    cloudwatch.stubber.assert_no_pending_responses()


# An unreadable slot fails the run (exit ≠ 0, the `task_failed` rule warns) naming the slot, never
# what it holds, and nothing is published: not even the days of the other slot.


def test_a_wrong_password_fails_naming_the_slot_and_publishes_nothing(
    empty_slots, cloudwatch, caplog
):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(timedelta(days=90) + HALF_DAY)
    contents = seal(timedelta(days=200), password="the-right-one")
    empty_slots.FISCAL_SEAL_NEXT_P12_BASE64 = contents
    empty_slots.FISCAL_SEAL_NEXT_PASSWORD = "a-wrong-password"

    with caplog.at_level(logging.DEBUG), pytest.raises(CommandError) as error:
        run()

    message = str(error.value)
    assert "next" in message
    for secret in ("a-wrong-password", "the-right-one", contents, contents[:40]):
        assert secret not in message
        assert secret not in caplog.text
    assert error.value.__cause__ is None and error.value.__suppress_context__
    assert cloudwatch.created == []


def test_bad_base64_fails_naming_the_slot(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = "not*base64*at*all"

    with pytest.raises(CommandError, match="current") as error:
        run()

    assert "not*base64" not in str(error.value)
    assert cloudwatch.created == []


def test_a_p12_without_a_certificate_fails_naming_the_slot(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(
        timedelta(days=90), certificate=False
    )

    with pytest.raises(CommandError, match="current"):
        run()

    assert cloudwatch.created == []


def test_a_failed_publication_fails_the_run(empty_slots, cloudwatch):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(timedelta(days=90) + HALF_DAY)
    cloudwatch.stubber.add_client_error(
        "put_metric_data", service_error_code="AccessDenied", http_status_code=403
    )

    with pytest.raises(CommandError, match="SealDaysToExpiry"):
        run()


def test_a_run_holding_the_lock_means_this_one_publishes_nothing(
    empty_slots, cloudwatch, other_session
):
    empty_slots.FISCAL_SEAL_CURRENT_P12_BASE64 = seal(timedelta(days=90) + HALF_DAY)
    other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")
    try:
        output = run()
    finally:
        other_session.execute(f"SELECT pg_advisory_unlock({LOCK_KEY})")

    assert cloudwatch.created == []
    assert "already running" in output
