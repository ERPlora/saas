"""Events of hubs (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, cited by live.py.

hubs reacts to no event of another app, so this module only names its own.
"""

BUSINESS_CREATED = "hubs.business.created"
BUSINESS_UPDATED = "hubs.business.updated"
BUSINESS_READY = "hubs.business.ready"
BUSINESS_OPENED = "hubs.business.opened"
BUSINESS_DELETED = "hubs.business.deleted"
BUSINESS_RESTORED = "hubs.business.restored"
#: The Hub refused a call about the business, or a later one succeeded: «Preparing» ↔ «Error».
BUSINESS_HUB_ERROR_CHANGED = "hubs.business.hub_error_changed"

BUSINESS = [
    BUSINESS_CREATED,
    BUSINESS_UPDATED,
    BUSINESS_READY,
    BUSINESS_OPENED,
    BUSINESS_DELETED,
    BUSINESS_RESTORED,
    BUSINESS_HUB_ERROR_CHANGED,
]

MEMBER_INVITED = "hubs.member.invited"
MEMBER_ROLE_CHANGED = "hubs.member.role_changed"
MEMBER_REMOVED = "hubs.member.removed"
MEMBER_INVITATION_RESENT = "hubs.member.invitation_resent"
MEMBER_INVITATION_CANCELLED = "hubs.member.invitation_cancelled"

MEMBER = [MEMBER_INVITED, MEMBER_ROLE_CHANGED, MEMBER_REMOVED, MEMBER_INVITATION_RESENT, MEMBER_INVITATION_CANCELLED]

INVITATION_ACCEPTED = "hubs.invitation.accepted"
INVITATION_DECLINED = "hubs.invitation.declined"

INVITATION = [INVITATION_ACCEPTED, INVITATION_DECLINED]

OWNERSHIP_REQUESTED = "hubs.ownership.requested"
OWNERSHIP_ACCEPTED = "hubs.ownership.accepted"
OWNERSHIP_DECLINED = "hubs.ownership.declined"
OWNERSHIP_CANCELLED = "hubs.ownership.cancelled"

OWNERSHIP = [OWNERSHIP_REQUESTED, OWNERSHIP_ACCEPTED, OWNERSHIP_DECLINED, OWNERSHIP_CANCELLED]

BILLING_PROFILE_UPDATED = "hubs.billing_profile.updated"

#: The people of a business changed (an invitation, its answer, a role, a removal): recorded on the channel
#: of every owner and admin of the business and of the account it touched, not only the actor's
#: (``services.notify_people``), so their lists re-run at once. Payload ``{"business_id"}``.
MEMBER_CHANGED = "hubs.member.changed"
#: An ownership offer was made, accepted, declined or cancelled: same channels as ``MEMBER_CHANGED``.
OWNERSHIP_CHANGED = "hubs.ownership.changed"

PEOPLE = [MEMBER_CHANGED, OWNERSHIP_CHANGED]

ALL = [*BUSINESS, *MEMBER, *INVITATION, *OWNERSHIP, BILLING_PROFILE_UPDATED, *PEOPLE]
