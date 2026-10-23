"""The events of hubs (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

hubs reacts to no event of another app: ``events.py`` only names its own, and every one of them is
recorded by some command (none is dead weight in ``live.py``).
"""

import re
from pathlib import Path

import pytest
from django.utils import timezone
from live.models import OutboxEvent
from live.operations import NAME_RE

from hubs import events, services
from hubs.models import Hub, HubOwnershipTransfer
from hubs.schemas import BusinessDeleteIn, BusinessOpenIn, ByIdIn, MemberInviteIn, MemberRoleIn, OwnershipTransferIn
from hubs.tests.conftest import ctx_for, member_of

SERVICES_SOURCE = (Path(events.__file__).parent / "services.py").read_text()


def test_every_event_is_named_app_entity_fact_and_belongs_to_hubs():
    assert events.ALL
    for name in events.ALL:
        assert NAME_RE.match(name) and name.startswith("hubs."), name


def test_events_are_listed_once():
    assert len(events.ALL) == len(set(events.ALL))


def test_every_event_is_recorded_by_a_command():
    """By the command itself (``record_event``) or, for the people of a business, on the channels of its
    owner and admins (``notify_people``, which runs the system command ``hubs.business.notify_people``)."""
    constants = {value: key for key, value in vars(events).items() if isinstance(value, str) and value in events.ALL}
    recorded = set(re.findall(r"record_event\(ctx, events\.([A-Z_]+)", SERVICES_SOURCE))
    recorded |= set(re.findall(r"notify_people\(ctx, events\.([A-Z_]+)", SERVICES_SOURCE))

    assert {constants[name] for name in events.ALL} == recorded


# --- Each write records its own event, once, for its business (the «Sale» of each flow) -----------------


def _open(team, business):
    Hub.objects.filter(pk=business.pk).update(status=Hub.Status.ACTIVE, ready_at=timezone.now())
    services.business_open(ctx_for(team["owner"]), BusinessOpenIn(id=business.id))


def _restore(team, business):
    services.business_delete(ctx_for(team["owner"]), BusinessDeleteIn(id=business.id, confirm_name=business.name))
    services.business_restore(ctx_for(team["owner"]), ByIdIn(id=business.id))


def _invitee(business, team):
    return member_of(business, team["invitee"]).id


def _offer(team, business):
    services.ownership_transfer(
        ctx_for(team["owner"]), OwnershipTransferIn(hub_id=business.id, member_id=member_of(business, team["admin"]).id)
    )
    return HubOwnershipTransfer.objects.get(hub=business).id


WRITES = {
    # HUBS-F11
    events.BUSINESS_OPENED: _open,
    # HUBS-F19
    events.BUSINESS_RESTORED: _restore,
    # HUBS-F24
    events.MEMBER_INVITED: lambda team, business: services.member_invite(
        ctx_for(team["owner"]), MemberInviteIn(hub_id=business.id, email="new@example.com")
    ),
    events.MEMBER_INVITATION_RESENT: lambda team, business: services.member_resend(
        ctx_for(team["owner"]), ByIdIn(id=_invitee(business, team))
    ),
    events.MEMBER_INVITATION_CANCELLED: lambda team, business: services.member_cancel(
        ctx_for(team["owner"]), ByIdIn(id=_invitee(business, team))
    ),
    # HUBS-F25
    events.INVITATION_ACCEPTED: lambda team, business: services.invitation_accept(
        ctx_for(team["invitee"]), ByIdIn(id=_invitee(business, team))
    ),
    events.INVITATION_DECLINED: lambda team, business: services.invitation_decline(
        ctx_for(team["invitee"]), ByIdIn(id=_invitee(business, team))
    ),
    # HUBS-F26
    events.MEMBER_ROLE_CHANGED: lambda team, business: services.member_change_role(
        ctx_for(team["owner"]), MemberRoleIn(id=member_of(business, team["employee"]).id, role="hub_manager")
    ),
    # HUBS-F27
    events.MEMBER_REMOVED: lambda team, business: services.member_remove(
        ctx_for(team["owner"]), ByIdIn(id=member_of(business, team["employee"]).id)
    ),
    # HUBS-F28
    events.OWNERSHIP_REQUESTED: _offer,
    events.OWNERSHIP_ACCEPTED: lambda team, business: services.ownership_accept(
        ctx_for(team["admin"]), ByIdIn(id=_offer(team, business))
    ),
    events.OWNERSHIP_DECLINED: lambda team, business: services.ownership_decline(
        ctx_for(team["admin"]), ByIdIn(id=_offer(team, business))
    ),
    events.OWNERSHIP_CANCELLED: lambda team, business: services.ownership_cancel(
        ctx_for(team["owner"]), ByIdIn(id=_offer(team, business))
    ),
}


@pytest.mark.django_db
@pytest.mark.parametrize("name", WRITES)
def test_each_write_records_its_own_event_once_for_its_business(name, team, business):
    """The flows promise these events in «Sale» (HUBS-F11, F19, F24–F28); the live lists hear the people's channel
    events instead, so nothing else notices if one is not recorded."""
    WRITES[name](team, business)

    (event,) = OutboxEvent.objects.filter(name=name)
    assert str(business.id) in (event.payload.get("hub_id"), event.payload.get("id"))
