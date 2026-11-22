"""``manage.py check_custom_domains`` as a command: what it prints, the metric it publishes, its lock and when a run
ends in error."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from hubs import domain_checks
from hubs.models import CustomDomain
from hubs.tests.conftest import DOMAIN, certificate_arn, pointing
from hubs.tests.custom_domain_states import (
    ARN,
    State,
    active,
    hub_of,
    pending,
    row_of,
    run_pass,
    second_business,
)

pytestmark = pytest.mark.django_db

LOCK_KEY = "hashtext('erplora.saas.check_custom_domains')"


# --- The metric and the command ------------------------------------------------------------------------


def run_command(*args):
    out = StringIO()
    call_command("check_custom_domains", *args, stdout=out)
    return out.getvalue()


def test_the_metric_counts_the_certificates_on_the_listener(standard_business, world, make_user):
    other = second_business(make_user)
    CustomDomain.objects.create(hub=other, hostname="www.otro.es", state=State.REMOVING, certificate_arn=certificate_arn(2), attached_at=timezone.now())
    world.expect_detach(arn=certificate_arn(2))
    world.expect_delete(arn=certificate_arn(2))
    active(standard_business, failures=0)

    run_pass(world, attached=1)


def test_the_metric_says_zero_too(world):
    run_pass(world, attached=0)


def test_the_command_says_what_it_did_and_publishes(standard_business, world, dns_world):
    active(standard_business)
    pointing(dns_world, standard_business)
    world.expect_metric(1)

    out = run_command()

    assert "check_custom_domains:" in out
    assert "checked=1" in out


@pytest.mark.parametrize("variable", [False, None], ids=["false", "absent"])
def test_with_the_variable_off_the_command_looks_at_nothing(settings, aws_edge, dns_world, standard_business, variable):
    """A domain there from before stays as it is: no call, no DNS, no metric, no snapshot."""
    settings.CUSTOM_DOMAINS_ENABLED = bool(variable)
    now = timezone.now()
    CustomDomain.objects.create(hub=standard_business, hostname=DOMAIN, state=State.ACTIVE, failures=2, certificate_arn=ARN, attached_at=now, proven_at=now)
    dns_world[(DOMAIN, "CNAME")] = AssertionError("nobody looks at the DNS")
    version = hub_of(standard_business).state_version

    out = run_command()

    assert "nothing done" in out
    row = row_of(standard_business)
    assert (row.state, row.failures) == (State.ACTIVE, 2)
    assert hub_of(standard_business).state_version == version


def test_one_domain_that_breaks_never_stops_the_pass_and_the_run_ends_in_error(
    standard_business, world, dns_world, make_user, monkeypatch
):
    mine, theirs = standard_business, second_business(make_user)
    active(mine)
    now = timezone.now()
    CustomDomain.objects.create(hub=theirs, hostname="www.otro.es", state=State.ACTIVE, certificate_arn=certificate_arn(2), attached_at=now, proven_at=now, activated_at=now)
    pointing(dns_world, theirs, domain="www.otro.es")
    real = domain_checks.points_at

    def breaks_for_mine(domain, target):
        if domain == DOMAIN:
            raise RuntimeError("a bug")
        return real(domain, target)

    monkeypatch.setattr(domain_checks, "points_at", breaks_for_mine)
    world.expect_metric(2)

    with pytest.raises(CommandError, match="crashed=1"):
        run_command()

    assert row_of(theirs).checked_at is not None


def test_a_metric_that_cannot_be_published_ends_the_run_in_error_after_the_pass(standard_business, world, dns_world):
    active(standard_business)
    pointing(dns_world, standard_business)
    world.cloudwatch.add_client_error("put_metric_data", "AccessDenied", "no")

    with pytest.raises(CommandError, match="metric"):
        run_command()

    assert row_of(standard_business).checked_at is not None


def test_a_second_run_returns_at_once(world, other_session):
    other_session.execute(f"SELECT pg_advisory_lock({LOCK_KEY})")

    assert "already running" in run_command()


def test_aws_or_the_hub_being_away_is_no_error_of_the_run(standard_business, world):
    """They come back: the next pass tries again, and a failed task every hour of an AWS incident is not news."""
    pending(standard_business, certificate_arn=ARN)
    world.acm.add_client_error("describe_certificate", "ThrottlingException", "later")
    world.expect_metric(0)

    assert "aws_unavailable=1" in run_command()
