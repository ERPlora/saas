"""``is_payer`` on a business's row and page: the account owns the business's payer (``hub.billing_profile``).

The payer is somebody's (PLAN-SAAS §3.1): the owner who set it up keeps it after handing the business over,
until the new owner writes its own (``hubs.billing_profile.update``). accounts reads the flag through
``hubs.business.list`` to refuse deleting an account that still pays for a live business.
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
