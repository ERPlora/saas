"""The SaaS's calls to ACM and to the ALB for a business's own domain (HUBS-F17; ``aws`` README, «Dominio propio de un
negocio»). Plain AWS, no ORM: callers keep what comes back (``hubs.services``), as ``hub_client`` does with the Hub.

The roles of ``saas`` and ``saas-cron`` have exactly these calls, conditioned: ``RequestCertificate`` by DNS with the one
tag ``Purpose=custom-domain``, ``DescribeCertificate`` and ``DeleteCertificate`` only on certificates with it, and
``AddListenerCertificates`` and ``RemoveListenerCertificates`` only on ``CUSTOM_DOMAINS_LISTENER_ARN``. There is no
``ListCertificates`` nor ``DescribeListenerCertificates``: what is attached is counted by our own rows.

Three answers mean something: ``TooManyCertificates`` (the listener at its quota: the domain waits, and is tried again in
the next check), ``CertificateInUse`` (the ALB has not let go of it yet: the deletion is tried again) and a certificate
that is already gone, which is what was asked for. Anything else, ``EdgeUnavailable``, names AWS's code: an
``AccessDenied`` on the first real domain is the policy's (aws#46), and the log has to say so.
"""

from dataclasses import dataclass
from functools import cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

#: What IAM reads to tell a customer's certificate from the platform's own (``custom_domains.tf``): one tag, no other.
CERTIFICATE_TAG = {"Key": "Purpose", "Value": "custom-domain"}
METRIC_NAMESPACE = "ERPlora/CustomDomains"
METRIC_CERTIFICATES_ATTACHED = "CertificatesAttached"

#: A pass walks every domain and a request holds its owner's page: never boto3's 60 s to connect and 60 to read.
_AWS_CONFIG = Config(connect_timeout=3, read_timeout=5, retries={"mode": "standard", "total_max_attempts": 2})


class EdgeUnavailable(Exception):
    """AWS did not do it: no connection, throttled or denied. The message names its code; the next check tries again."""


class TooManyCertificates(Exception):
    """The listener holds all the certificates its quota allows."""


class CertificateInUse(Exception):
    """The ALB has not let go of the certificate yet."""


@dataclass(frozen=True)
class CertificateFacts:
    status: str
    #: The CNAME that validates the certificate and renews it; empty for the few seconds until ACM has it.
    validation_name: str = ""
    validation_value: str = ""
    #: Why it failed (``CAA_ERROR``…), when its status is ``FAILED``.
    failure_reason: str = ""


def request_certificate(domain: str, token: str) -> str:
    """The ARN of a certificate for ``domain``; ``token``, the row's, gives back the same one for an hour."""
    answer = _asking_acm(
        lambda acm: acm.request_certificate(
            DomainName=domain,
            ValidationMethod="DNS",
            IdempotencyToken=token,
            Tags=[CERTIFICATE_TAG],
        )
    )
    return answer["CertificateArn"]


def describe_certificate(arn: str) -> CertificateFacts:
    certificate = _asking_acm(lambda acm: acm.describe_certificate(CertificateArn=arn))["Certificate"]
    options = certificate.get("DomainValidationOptions") or [{}]
    record = options[0].get("ResourceRecord") or {}
    return CertificateFacts(
        status=certificate["Status"],
        validation_name=record.get("Name", "").removesuffix("."),
        validation_value=record.get("Value", "").removesuffix("."),
        failure_reason=certificate.get("FailureReason", ""),
    )


def delete_certificate(arn: str) -> None:
    """Delete the certificate; one that is gone is done. ``CertificateInUse`` while the ALB holds it."""
    try:
        _acm().delete_certificate(CertificateArn=arn)
    except ClientError as error:
        code = _code(error)
        if code == "ResourceInUseException":
            raise CertificateInUse(arn) from None
        if code != "ResourceNotFoundException":
            raise _unavailable(error) from None
    except BotoCoreError as error:
        raise _unavailable(error) from None


def attach(arn: str) -> None:
    """Put the certificate on the shared listener by SNI (idempotent); ``TooManyCertificates`` at its quota."""
    try:
        _elbv2().add_listener_certificates(
            ListenerArn=settings.CUSTOM_DOMAINS_LISTENER_ARN, Certificates=[{"CertificateArn": arn}]
        )
    except ClientError as error:
        if _code(error) == "TooManyCertificates":
            raise TooManyCertificates(arn) from None
        raise _unavailable(error) from None
    except BotoCoreError as error:
        raise _unavailable(error) from None


def detach(arn: str) -> None:
    """Take the certificate off the shared listener; one it no longer has is done."""
    try:
        _elbv2().remove_listener_certificates(
            ListenerArn=settings.CUSTOM_DOMAINS_LISTENER_ARN, Certificates=[{"CertificateArn": arn}]
        )
    except ClientError as error:
        if _code(error) != "CertificateNotFound":
            raise _unavailable(error) from None
    except BotoCoreError as error:
        raise _unavailable(error) from None


def publish_certificates_attached(count: int) -> None:
    """``ERPlora/CustomDomains CertificatesAttached``: the alarm at 80 % of the listener reads it, no AWS metric does."""
    try:
        _cloudwatch().put_metric_data(
            Namespace=METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": METRIC_CERTIFICATES_ATTACHED,
                    "Dimensions": [{"Name": "Environment", "Value": settings.ERPLORA_ENVIRONMENT}],
                    "Value": float(count),
                    "Unit": "Count",
                }
            ],
        )
    except (BotoCoreError, ClientError) as error:
        raise _unavailable(error) from None


def _asking_acm(call):
    try:
        return call(_acm())
    except (BotoCoreError, ClientError) as error:
        raise _unavailable(error) from None


def _code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


def _unavailable(error: BotoCoreError | ClientError) -> EdgeUnavailable:
    code = _code(error) if isinstance(error, ClientError) else type(error).__name__
    return EdgeUnavailable(f"{code}: {error}")


@cache
def _acm():
    return boto3.client("acm", region_name=settings.AWS_REGION, config=_AWS_CONFIG)


@cache
def _elbv2():
    return boto3.client("elbv2", region_name=settings.AWS_REGION, config=_AWS_CONFIG)


@cache
def _cloudwatch():
    return boto3.client("cloudwatch", region_name=settings.AWS_REGION, config=_AWS_CONFIG)
