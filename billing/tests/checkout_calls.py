"""What the checkout tests share: the two operations called as the owner would call them, what Stripe was sent,
the payer's form saved again, a refusal by its code, a business that already pays and one handed over to a new
owner.
"""

import pytest
from django.utils import timezone
from live.errors import OperationError

from billing.schemas import CheckoutConfirmIn, CheckoutStartIn
from billing.services import checkouts, plan_changes
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import item, subscription

NOW_TS = int(timezone.now().timestamp())


def start(user, hub, **selection):
    return checkouts.checkout_start(
        ctx_for(user), CheckoutStartIn(hub_id=hub.id, **selection)
    ).model_dump()


def confirm(user, hub, **selection):
    return plan_changes.checkout_confirm(
        ctx_for(user), CheckoutConfirmIn(hub_id=hub.id, **selection)
    ).model_dump()


def session_params(double):
    return double.last("checkout.sessions.create").params


def payer(hub, **fields):
    """The payer's form saved again (read fresh: what the platform wrote meanwhile stays)."""
    from hubs.models import BillingProfile

    profile = BillingProfile.objects.get(pk=hub.billing_profile_id)
    hub.billing_profile = profile
    for field, value in fields.items():
        setattr(profile, field, value)
    profile.save()
    return hub


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()
    return error.value


def paying(shop, stripe_double, **live):
    paid = pay(shop)
    stripe_double.answer(
        "subscriptions.retrieve",
        subscription(
            "sub_1",
            customer="cus_1",
            items=[item("si_plan", "price_starter_month")],
            **live,
        ),
    )
    return paid


def transferred(hub, old_owner, make_user):
    """The business after an accepted transfer: a new owner, the payer still the previous owner's."""
    from hubs.models import HubMember

    new_owner = make_user("new-owner@example.com", language="es")
    HubMember.objects.filter(hub=hub, user=old_owner).delete()
    now = timezone.now()
    HubMember.objects.create(hub=hub, user=new_owner, role=HubMember.Role.OWNER, joined_at=now, accepted_at=now)
    return new_owner
