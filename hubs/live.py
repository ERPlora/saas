"""Live queries of hubs and the events that re-run them after the COMMIT (plan 2026-10-13 §3, live data).

The scope is the account (PLAN-SAAS §6): a command notifies the channel of the account that ran it, so
each list re-runs for that account. A change of the people of a business also reaches the owner, the
admins and the account it touched (``events.PEOPLE``, L1-A2); anybody else sees a change at the 300 s
safety re-run or on reload.
"""

from live.live_registry import live

from hubs import events

live(
    "hubs.business.list",
    on=[
        *events.BUSINESS,
        events.INVITATION_ACCEPTED,
        events.INVITATION_DECLINED,
        *events.OWNERSHIP,
        *events.PEOPLE,
    ],
)
live(
    "hubs.business.get",
    on=[
        events.BUSINESS_UPDATED,
        events.BUSINESS_READY,
        events.BUSINESS_DELETED,
        events.BUSINESS_RESTORED,
        events.BUSINESS_HUB_ERROR_CHANGED,
        *events.MEMBER,
        events.INVITATION_ACCEPTED,
        *events.OWNERSHIP,
        events.BILLING_PROFILE_UPDATED,
        *events.PEOPLE,
    ],
)
live(
    "hubs.member.list",
    on=[
        *events.MEMBER,
        *events.INVITATION,
        *events.OWNERSHIP,
        events.BUSINESS_DELETED,
        events.BUSINESS_RESTORED,
        *events.PEOPLE,
    ],
)
live(
    "hubs.invitation.list_mine",
    on=[*events.INVITATION, events.MEMBER_INVITED, events.MEMBER_INVITATION_CANCELLED, *events.PEOPLE],
)
