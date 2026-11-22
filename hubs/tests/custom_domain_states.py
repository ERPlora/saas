"""What the tests of ``manage.py check_custom_domains`` share: a domain's row in each state, one pass of the check
and a second business on the plan that includes an own domain."""

from django.utils import timezone

from hubs import services
from hubs.models import CustomDomain, Hub, Plan, Subscription
from hubs.tests.conftest import DOMAIN, certificate_arn, create_business

ARN = certificate_arn()
State = CustomDomain.State
Reason = CustomDomain.Reason


def run_pass(world, *, attached=0):
    """One pass, with the metric it publishes at its end."""
    world.expect_metric(attached)
    counts = services.custom_domain_checks.check_custom_domains()
    return counts


def row_of(hub):
    return CustomDomain.objects.get(hub=hub)


def hub_of(hub):
    return Hub.objects.get(pk=hub.pk)


def pending(hub, **fields):
    return CustomDomain.objects.create(hub=hub, hostname=DOMAIN, **fields)


def certificate_issued(hub, **fields):
    """A pending domain whose certificate is on its way to the listener."""
    return pending(hub, certificate_arn=ARN, validation_name="_a", validation_value="_b", **fields)


def attached(hub, **fields):
    return certificate_issued(hub, attached_at=timezone.now(), **fields)


def active(hub, **fields):
    now = timezone.now()
    row = attached(hub, state=State.ACTIVE, proven_at=now, activated_at=now, **fields)
    Hub.objects.filter(pk=hub.pk).update(pushed_state_version=hub_of(hub).state_version)
    return row


def state_pushes(hub_double):
    return hub_double.calls_to("PUT", "/state")


def second_business(make_user):
    other = create_business(make_user("otra@example.com"), name="Otro")
    Subscription.objects.filter(hub=other).update(plan=Plan.objects.get(slug="standard"))
    Hub.objects.filter(pk=other.pk).update(status=Hub.Status.ACTIVE, pending_hub_call="")
    return Hub.objects.get(pk=other.pk)
