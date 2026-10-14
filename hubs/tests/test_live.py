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


# --- Changes of people reach every manager of the business at once (L1-A2) ------------------------
#
# A member or ownership command notifies the actor's channel with its own event (kept as it was), and
# also ``hubs.member.changed`` / ``hubs.ownership.changed`` on the channel of every owner and admin of the
# business and of the account it touched (``hubs.business.notify_people``, a system command, one per
# channel): the owner's members page re-runs when somebody else accepts, without waiting for the 300 s
# safety re-run.

from hubs import services  # noqa: E402
from hubs.schemas import MemberInviteIn, MemberRoleIn, OwnershipTransferIn  # noqa: E402
from hubs.tests.conftest import member_of  # noqa: E402

PEOPLE_LISTS = {"hubs.member.list", "hubs.business.get", "hubs.business.list", "hubs.invitation.list_mine"}


def test_a_change_of_people_re_runs_every_list_that_shows_them():
    assert PEOPLE_LISTS <= live_registry.affected([events.MEMBER_CHANGED])
    assert PEOPLE_LISTS <= live_registry.affected([events.OWNERSHIP_CHANGED])


@pytest.fixture
def notified(monkeypatch):
    """``(channel key, event names)`` of every notification after a COMMIT, as the live stream gets them."""
    from live import operations

    sent = []
    monkeypatch.setattr(operations, "notify_hook", lambda scope, names: sent.append((scope.key, sorted(names))))
    return sent


def channels(notified, event):
    return {key for key, names in notified if event in names}


@pytest.mark.django_db
class TestEveryManagerHearsIt:
    def test_another_account_accepting_re_runs_the_owners_and_admins_lists(
        self, business, team, notified, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            services.invitation_accept(ctx_for(team["invitee"]), ByIdIn(id=member_of(business, team["invitee"]).id))

        assert channels(notified, events.MEMBER_CHANGED) == {str(team["owner"].pk), str(team["admin"].pk)}
        # The actor keeps its own event on its own channel, as before.
        assert (str(team["invitee"].pk), [events.INVITATION_ACCEPTED]) in notified
        assert PEOPLE_LISTS <= live_registry.affected([events.MEMBER_CHANGED])

    def test_the_event_names_its_business(self, business, team, django_capture_on_commit_callbacks):
        from live.models import OutboxEvent

        services.invitation_accept(ctx_for(team["invitee"]), ByIdIn(id=member_of(business, team["invitee"]).id))

        rows = OutboxEvent.objects.filter(name=events.MEMBER_CHANGED)
        assert {(row.scope_key, row.actor) for row in rows} == {(str(team["owner"].pk), "system"), (str(team["admin"].pk), "system")}
        assert {row.payload["business_id"] for row in rows} == {str(business.id)}

    def test_a_decline_re_runs_the_managers_lists(self, business, team, notified, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            services.invitation_decline(ctx_for(team["invitee"]), ByIdIn(id=member_of(business, team["invitee"]).id))

        assert channels(notified, events.MEMBER_CHANGED) == {str(team["owner"].pk), str(team["admin"].pk)}

    @pytest.mark.parametrize(
        ("command", "target"),
        [("change_role", "manager"), ("remove", "employee"), ("resend", "invitee"), ("cancel", "invitee")],
    )
    def test_a_managers_write_reaches_the_other_managers_and_the_person_it_touched(
        self, business, team, notified, django_capture_on_commit_callbacks, command, target
    ):
        row = member_of(business, team[target])
        with django_capture_on_commit_callbacks(execute=True):
            if command == "change_role":
                services.member_change_role(ctx_for(team["admin"]), MemberRoleIn(id=row.id, role="hub_employee"))
            else:
                getattr(services, f"member_{command}")(ctx_for(team["admin"]), ByIdIn(id=row.id))

        assert channels(notified, events.MEMBER_CHANGED) == {str(team["owner"].pk), str(team[target].pk)}

    def test_an_invitation_reaches_the_managers_and_the_invited_account(
        self, business, team, notified, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            services.member_invite(
                ctx_for(team["owner"]), MemberInviteIn(hub_id=business.id, email=team["stranger"].email, role="hub_employee")
            )

        assert channels(notified, events.MEMBER_CHANGED) == {str(team["admin"].pk), str(team["stranger"].pk)}

    def test_a_managers_and_employees_lists_are_not_disturbed(
        self, business, team, notified, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            services.invitation_accept(ctx_for(team["invitee"]), ByIdIn(id=member_of(business, team["invitee"]).id))

        assert not channels(notified, events.MEMBER_CHANGED) & {str(team["manager"].pk), str(team["employee"].pk)}

    def test_a_refused_write_tells_nobody(self, business, team, notified, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True), pytest.raises(PermissionDenied):
            services.member_remove(ctx_for(team["manager"]), ByIdIn(id=member_of(business, team["employee"]).id))

        assert notified == []


@pytest.mark.django_db
class TestOwnershipChangesAreHeard:
    def offer(self, business, team):
        return services.ownership_transfer(
            ctx_for(team["owner"]), OwnershipTransferIn(hub_id=business.id, member_id=member_of(business, team["manager"]).id)
        )

    def test_an_offer_reaches_the_recipient_and_the_admins(
        self, business, team, notified, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            self.offer(business, team)

        assert channels(notified, events.OWNERSHIP_CHANGED) == {str(team["admin"].pk), str(team["manager"].pk)}

    def test_accepting_reaches_the_old_owner_and_the_admins(
        self, business, team, notified, django_capture_on_commit_callbacks
    ):
        offer = self.offer(business, team)
        with django_capture_on_commit_callbacks(execute=True):
            services.ownership_accept(ctx_for(team["manager"]), ByIdIn(id=offer.id))

        assert channels(notified, events.OWNERSHIP_CHANGED) == {str(team["owner"].pk), str(team["admin"].pk)}

    def test_declining_reaches_the_owner_and_the_admins(self, business, team, notified, django_capture_on_commit_callbacks):
        offer = self.offer(business, team)
        with django_capture_on_commit_callbacks(execute=True):
            services.ownership_decline(ctx_for(team["manager"]), ByIdIn(id=offer.id))

        assert channels(notified, events.OWNERSHIP_CHANGED) == {str(team["owner"].pk), str(team["admin"].pk)}

    def test_cancelling_reaches_the_recipient_and_the_admins(
        self, business, team, notified, django_capture_on_commit_callbacks
    ):
        offer = self.offer(business, team)
        with django_capture_on_commit_callbacks(execute=True):
            services.ownership_cancel(ctx_for(team["owner"]), ByIdIn(id=offer.id))

        assert channels(notified, events.OWNERSHIP_CHANGED) == {str(team["admin"].pk), str(team["manager"].pk)}


@pytest.mark.django_db
def test_only_the_platform_notifies_people(business, owner):
    from hubs.schemas import NotifyPeopleIn

    with pytest.raises(PermissionDenied):
        services.business_notify_people(ctx_for(owner), NotifyPeopleIn(id=business.id, event=events.MEMBER_CHANGED))
