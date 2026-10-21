"""``is_payer`` on a business's row and page: the account owns the business's payer (``hub.billing_profile``).

The payer is somebody's (PLAN-SAAS §3.1): the owner who set it up keeps it after handing the business over,
until the new owner writes its own (``hubs.billing_profile.update``). Since saas#2587 the flag is ``still_pays``: it
also holds when the plan's Stripe subscription is still charged to a customer of one of the account's own payers
after a hand-over. accounts reads the flag through ``hubs.business.list`` to refuse deleting an account that still
pays for a live business, and ``hubs.member.remove`` refuses to take that person out of it.
"""

import pytest

from hubs import queries
from hubs.models import BillingProfile, Hub, HubMember
from hubs.schemas import BusinessListIn, ByIdIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


def row(user, business):
    page = queries.business_list(ctx_for(user), BusinessListIn())
    return next(row for row in page.rows if row.id == business.id)


def page(user, business):
    return queries.business_get(ctx_for(user), ByIdIn(id=business.id))


def test_the_owner_who_set_up_the_payer_pays(business, owner):
    assert business.billing_profile.owner_id == owner.pk

    assert (row(owner, business).is_payer, page(owner, business).is_payer) == (True, True)


def test_an_admin_does_not(business, team):
    assert (row(team["admin"], business).is_payer, page(team["admin"], business).is_payer) == (False, False)


def test_the_payer_is_whoever_owns_it_not_the_role(business, team, owner):
    """After a hand-over the old owner still pays until the new one writes its own payer."""
    HubMember.objects.filter(hub=business, user=owner).update(role=HubMember.Role.ADMIN)
    HubMember.objects.filter(hub=business, user=team["admin"]).update(role=HubMember.Role.OWNER)

    assert (row(owner, business).is_payer, row(team["admin"], business).is_payer) == (True, False)


def test_without_a_payer_nobody_pays(business, owner):
    Hub.objects.filter(pk=business.pk).update(billing_profile=None)
    BillingProfile.objects.filter(owner=owner).delete()

    assert row(owner, business).is_payer is False


def test_the_row_names_the_payer_to_whoever_pays_only(business, team, owner):
    """Audit 2 R-21: the Store warns about a declined card only when the business it sells to has the same payer
    (its Stripe customer) as the one whose card was declined; the row says which payer, to whoever pays."""
    assert row(owner, business).payer_id == business.billing_profile_id
    assert row(team["admin"], business).payer_id is None


def test_without_a_payer_the_row_names_none(business, owner):
    Hub.objects.filter(pk=business.pk).update(billing_profile=None)

    assert row(owner, business).payer_id is None


def test_the_card_that_still_pays_the_plan_after_a_hand_over_pays(business, team, owner):
    """saas#2587: the new owner wrote its own payer, but the plan's Stripe subscription is still charged to the old
    owner's customer until support moves it (``billing.payer_required``): the old owner still pays, on the row and
    on the page, so it can neither be taken out nor delete its account."""
    from billing.tests.conftest import pay
    from hubs import services
    from hubs.schemas import BillingProfileIn

    BillingProfile.objects.filter(pk=business.billing_profile_id).update(stripe_customer_id="cus_old")
    pay(business, customer="cus_old")
    HubMember.objects.filter(hub=business, user=owner).update(role=HubMember.Role.ADMIN)
    HubMember.objects.filter(hub=business, user=team["admin"]).update(role=HubMember.Role.OWNER)
    services.billing_profile_update(
        ctx_for(team["admin"]), BillingProfileIn(hub_id=business.id, billing_name="Adela SL")
    )

    assert (row(owner, business).is_payer, page(owner, business).is_payer) == (True, True)
    assert row(owner, business).payer_id is None


def test_a_plan_on_somebody_elses_card_holds_nobody(business, team, owner):
    """Only the account's own payers count: a plan charged to the owner's card does not make its admin or its
    manager a payer (they could neither be taken out nor delete their accounts otherwise)."""
    from billing.tests.conftest import pay

    BillingProfile.objects.filter(pk=business.billing_profile_id).update(stripe_customer_id="cus_owner")
    pay(business, customer="cus_owner")

    assert row(team["manager"], business).is_payer is False
    assert (row(team["admin"], business).is_payer, page(team["admin"], business).is_payer) == (False, False)
    assert row(owner, business).is_payer is True
