"""The live queries of hubs and the events that re-run them (plan 2026-10-13 §3, live data).

The scope is the account (PLAN-SAAS §6): each list re-runs for the account whose command changed it;
other accounts see the change at the 300 s safety re-run or on reload.
"""

import pytest
from live.errors import NotFound, PermissionDenied
from live.live_registry import live_registry
from live.operations import get

from hubs import events
from hubs.schemas import BusinessListIn, ByIdIn, InvitationListIn, MemberListIn
from hubs.tests.conftest import ctx_for

LIVE = {"hubs.business.list", "hubs.business.get", "hubs.member.list", "hubs.invitation.list_mine"}


def hubs_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("hubs.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_lists_of_the_panel_are_live():
    assert set(hubs_queries()) == LIVE


def test_every_live_query_needs_the_accounts_permission():
    """A live query needs a permission (live.E004); a visitor without an account holds none."""
    for name in LIVE:
        op = get(name)
        assert (op.kind, op.permission) == ("query", "hubs.view"), name


def test_every_event_cited_is_one_of_hubs():
    for on in hubs_queries().values():
        assert set(on) <= set(events.ALL)


def test_a_new_business_re_runs_the_list_of_businesses():
    assert "hubs.business.list" in live_registry.affected([events.BUSINESS_CREATED])


def test_a_ready_business_re_runs_its_list_and_its_page():
    assert {"hubs.business.list", "hubs.business.get"} <= live_registry.affected([events.BUSINESS_READY])


def test_a_refusal_of_the_hub_re_runs_the_list_and_the_page():
    """Recorded or cleared, the Hub's refusal changes «Preparing» into «Error» (or back) at once."""
    assert {"hubs.business.list", "hubs.business.get"} <= live_registry.affected([events.BUSINESS_HUB_ERROR_CHANGED])


def test_an_invitation_re_runs_the_members_not_the_businesses_of_who_invited():
    affected = live_registry.affected([events.MEMBER_INVITED])

    assert "hubs.member.list" in affected
    assert "hubs.business.list" not in affected


def test_an_accepted_invitation_re_runs_the_invitees_lists():
    assert {"hubs.business.list", "hubs.invitation.list_mine", "hubs.member.list"} <= live_registry.affected(
        [events.INVITATION_ACCEPTED]
    )


def test_an_accepted_transfer_re_runs_both_pages():
    assert {"hubs.business.list", "hubs.business.get", "hubs.member.list"} <= live_registry.affected(
        [events.OWNERSHIP_ACCEPTED]
    )


# --- A re-run is the same call, with the subscriber's context -------------------------------------

def inputs(hub_id):
    return {
        "hubs.business.list": BusinessListIn(),
        "hubs.business.get": ByIdIn(id=hub_id),
        "hubs.member.list": MemberListIn(hub_id=hub_id),
        "hubs.invitation.list_mine": InvitationListIn(),
    }


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(LIVE))
def test_a_visitor_without_an_account_subscribes_to_nothing(business, name):
    with pytest.raises(PermissionDenied):
        get(name)(ctx_for(None), inputs(business.id)[name])


@pytest.mark.django_db
def test_a_subscription_follows_the_role_at_each_run(business, team):
    """An employee's re-run of the members page is refused; a stranger's does not see the business."""
    with pytest.raises(PermissionDenied):
        get("hubs.member.list")(ctx_for(team["employee"]), MemberListIn(hub_id=business.id))
    with pytest.raises(NotFound):
        get("hubs.business.get")(ctx_for(team["stranger"]), ByIdIn(id=business.id))
    assert get("hubs.member.list")(ctx_for(team["admin"]), MemberListIn(hub_id=business.id)).total == 5
