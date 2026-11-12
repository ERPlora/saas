"""The SaaS's calls to ACM and to the ALB for a business's own domain (HUBS-F17; ``aws`` README, «Dominio propio de un
negocio»), against botocore's Stubber: it refuses a parameter the API does not take and any call it was not told of."""

import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from hubs import edge_client
from hubs.tests.conftest import fake_aws_client

ARN = "arn:aws:acm:eu-west-1:123456789012:certificate/0193a0a0-0000-7000-8000-000000000001"
LISTENER = "arn:aws:elasticloadbalancing:eu-west-1:123456789012:listener/app/erplora/abc/def"
TOKEN = "0193a0a000007000800000000000abcd"


@pytest.fixture
def acm(monkeypatch):
    client = fake_aws_client(monkeypatch, "acm")
    with Stubber(client) as stubber:
        monkeypatch.setattr(edge_client, "_acm", lambda: client)
        yield stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def alb(monkeypatch, settings):
    settings.CUSTOM_DOMAINS_LISTENER_ARN = LISTENER
    client = fake_aws_client(monkeypatch, "elbv2")
    with Stubber(client) as stubber:
        monkeypatch.setattr(edge_client, "_elbv2", lambda: client)
        yield stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def cloudwatch(monkeypatch):
    client = fake_aws_client(monkeypatch, "cloudwatch")
    with Stubber(client) as stubber:
        monkeypatch.setattr(edge_client, "_cloudwatch", lambda: client)
        yield stubber
        stubber.assert_no_pending_responses()


def test_a_certificate_is_asked_for_by_dns_with_exactly_one_tag_and_the_rows_token(acm):
    """IAM denies any other tag, any other method and, through ``acm:Export``, an exportable certificate."""
    acm.add_response(
        "request_certificate",
        {"CertificateArn": ARN},
        {
            "DomainName": "www.minegocio.es",
            "ValidationMethod": "DNS",
            "IdempotencyToken": TOKEN,
            "Tags": [{"Key": "Purpose", "Value": "custom-domain"}],
        },
    )
    assert edge_client.request_certificate("www.minegocio.es", TOKEN) == ARN


def _certificate(status="PENDING_VALIDATION", **extra):
    return {"Certificate": {"CertificateArn": ARN, "Status": status, **extra}}


def test_describing_a_certificate_gives_its_validation_record_without_the_final_dots(acm):
    acm.add_response(
        "describe_certificate",
        _certificate(
            DomainValidationOptions=[
                {
                    "DomainName": "www.minegocio.es",
                    "ResourceRecord": {
                        "Name": "_abc.www.minegocio.es.",
                        "Type": "CNAME",
                        "Value": "_def.acm-validations.aws.",
                    },
                }
            ]
        ),
        {"CertificateArn": ARN},
    )
    facts = edge_client.describe_certificate(ARN)
    assert facts.status == "PENDING_VALIDATION"
    assert (facts.validation_name, facts.validation_value) == ("_abc.www.minegocio.es", "_def.acm-validations.aws")
    assert facts.failure_reason == ""


@pytest.mark.parametrize(
    "options",
    [None, [{"DomainName": "www.minegocio.es"}]],
    ids=["no options yet", "option without its record yet"],
)
def test_the_validation_record_can_take_a_few_seconds_to_exist(acm, options):
    extra = {} if options is None else {"DomainValidationOptions": options}
    acm.add_response("describe_certificate", _certificate(**extra), {"CertificateArn": ARN})
    facts = edge_client.describe_certificate(ARN)
    assert (facts.validation_name, facts.validation_value) == ("", "")


def test_describing_a_certificate_that_failed_says_why(acm):
    acm.add_response(
        "describe_certificate", _certificate("FAILED", FailureReason="CAA_ERROR"), {"CertificateArn": ARN}
    )
    facts = edge_client.describe_certificate(ARN)
    assert (facts.status, facts.failure_reason) == ("FAILED", "CAA_ERROR")


def test_attaching_puts_one_certificate_on_the_listener_of_the_setting(alb):
    alb.add_response(
        "add_listener_certificates",
        {},
        {"ListenerArn": LISTENER, "Certificates": [{"CertificateArn": ARN}]},
    )
    edge_client.attach(ARN)


def test_the_listener_at_its_quota_is_said_apart(alb):
    alb.add_client_error("add_listener_certificates", "TooManyCertificates", "at the quota")
    with pytest.raises(edge_client.TooManyCertificates):
        edge_client.attach(ARN)


def test_detaching_takes_it_off_the_listener_of_the_setting(alb):
    alb.add_response(
        "remove_listener_certificates",
        {},
        {"ListenerArn": LISTENER, "Certificates": [{"CertificateArn": ARN}]},
    )
    edge_client.detach(ARN)


def test_detaching_a_certificate_the_listener_no_longer_has_is_done(alb):
    alb.add_client_error("remove_listener_certificates", "CertificateNotFound", "not there")
    edge_client.detach(ARN)


def test_deleting_a_certificate(acm):
    acm.add_response("delete_certificate", {}, {"CertificateArn": ARN})
    edge_client.delete_certificate(ARN)


def test_a_certificate_the_alb_has_not_let_go_of_is_said_apart(acm):
    acm.add_client_error("delete_certificate", "ResourceInUseException", "in use")
    with pytest.raises(edge_client.CertificateInUse):
        edge_client.delete_certificate(ARN)


def test_deleting_a_certificate_that_is_gone_is_done(acm):
    acm.add_client_error("delete_certificate", "ResourceNotFoundException", "gone")
    edge_client.delete_certificate(ARN)


@pytest.mark.parametrize("code", ["AccessDeniedException", "ThrottlingException", "LimitExceededException"])
def test_anything_else_from_acm_is_aws_being_unavailable_and_names_its_code(acm, code):
    """An AccessDenied on the first real domain is the policy's, and has to be readable in the log."""
    acm.add_client_error("request_certificate", code, "no")
    with pytest.raises(edge_client.EdgeUnavailable, match=code):
        edge_client.request_certificate("www.minegocio.es", TOKEN)


def test_anything_else_from_the_alb_is_aws_being_unavailable(alb):
    alb.add_client_error("add_listener_certificates", "AccessDenied", "no")
    with pytest.raises(edge_client.EdgeUnavailable, match="AccessDenied"):
        edge_client.attach(ARN)


def test_no_connection_is_aws_being_unavailable(monkeypatch):
    class NoConnection:
        def describe_certificate(self, **_):
            raise EndpointConnectionError(endpoint_url="https://acm.eu-west-1.amazonaws.com")

    monkeypatch.setattr(edge_client, "_acm", NoConnection)
    with pytest.raises(edge_client.EdgeUnavailable):
        edge_client.describe_certificate(ARN)


def test_the_certificates_attached_are_published_with_their_environment(cloudwatch, settings):
    settings.ERPLORA_ENVIRONMENT = "prod"
    cloudwatch.add_response(
        "put_metric_data",
        {},
        {
            "Namespace": "ERPlora/CustomDomains",
            "MetricData": [
                {
                    "MetricName": "CertificatesAttached",
                    "Dimensions": [{"Name": "Environment", "Value": "prod"}],
                    "Value": 7.0,
                    "Unit": "Count",
                }
            ],
        },
    )
    edge_client.publish_certificates_attached(7)


def test_a_metric_that_cannot_be_published_is_aws_being_unavailable(cloudwatch):
    cloudwatch.add_client_error("put_metric_data", "AccessDenied", "no")
    with pytest.raises(edge_client.EdgeUnavailable):
        edge_client.publish_certificates_attached(1)


def test_calling_aws_never_waits_for_botos_minutes(settings):
    """A pass walks every domain and a request holds its owner's page: boto3's default is 60 s to connect and 60 to read."""
    edge_client._acm.cache_clear()
    settings.AWS_REGION = "eu-west-1"
    client = edge_client._acm()
    assert client.meta.config.connect_timeout <= 5
    assert client.meta.config.read_timeout <= 10
    assert client.meta.region_name == "eu-west-1"
    edge_client._acm.cache_clear()
