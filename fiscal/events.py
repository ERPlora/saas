"""Events of fiscal (``<app>.<entity>.<fact>``): recorded by services.py in the outbox, cited by live.py.

Each step of an authorisation is its own event, recorded by the command that takes it, so the outbox is its
trail: who (``actor``), which business and which version (payload ``{"hub_id", "id", "version"}``; never a
document). ``REPRESENTATION_CHANGED`` is told on the channel of each owner and admin of the business
(``services.tell_the_business``), so the state on their page re-runs at once. fiscal reacts to no event of
another app.
"""

REPRESENTATION_SUBMITTED = "fiscal.representation.submitted"
REPRESENTATION_APPROVED = "fiscal.representation.approved"
REPRESENTATION_RETURNED = "fiscal.representation.returned"
REPRESENTATION_REVOKED = "fiscal.representation.revoked"

REPRESENTATION = [
    REPRESENTATION_SUBMITTED,
    REPRESENTATION_APPROVED,
    REPRESENTATION_RETURNED,
    REPRESENTATION_REVOKED,
]

#: The authorisation of a business changed: payload ``{"hub_id"}``, on an owner's or admin's channel.
REPRESENTATION_CHANGED = "fiscal.representation.changed"

ALL = [*REPRESENTATION, REPRESENTATION_CHANGED]
