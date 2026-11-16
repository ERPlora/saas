"""The businesses an account is on, read through ``hubs.business.list`` by its name: accounts never imports
hubs."""

from live import operations
from live.context import OperationContext

from accounts import queries


#: The businesses of an account, read through their operation (accounts never imports hubs).
BUSINESS_LIST = "hubs.business.list"


def businesses_holding(ctx: OperationContext) -> tuple[list[dict], list[dict]]:
    """``(owned, paid)``: the businesses that are not deleted which the caller owns, and those it pays for without
    owning them, as ``[{id, name}]``, from ``hubs.business.list``.

    A business has one owner, and its row says what that owner may do: ``can.delete`` is
    «the owner, not deleted». ``is_payer`` says the account still pays for it: it owns the business's payer, or the
    plan is still charged to its card after a hand-over (``hubs.queries.still_pays``); and a payer cannot be taken
    out of the business (``hubs.member_pays``), so the list sees it. A deleted business in its 90 days of recovery
    holds nobody (``deletion_requested_at``).
    """
    business_list = operations.get(BUSINESS_LIST)
    owned: list[dict] = []
    paid: list[dict] = []
    offset = 0
    while True:
        page = business_list(ctx, business_list.input(limit=100, offset=offset))
        for row in page.rows:
            entry = {"id": str(row.id), "name": row.name}
            if row.can.delete:
                owned.append(entry)
            elif row.is_payer and row.deletion_requested_at is None:
                paid.append(entry)
        offset += page.limit
        if offset >= page.total:
            return owned, paid


def on_a_business(user) -> bool:
    """Whether ``user`` is on a business in any way ``hubs.business.list`` sees (called by its name: accounts never
    imports hubs): a member, also of one in its days of recovery (a restore gives it back), or invited to one. Neither
    ``create_platform_user`` nor ``User.clean`` (the admin's form) makes such an account staff."""
    business_list = operations.get(BUSINESS_LIST)
    page = business_list(queries.as_account(user), business_list.input(limit=1, offset=0))
    return page.total > 0 or bool(page.invitations)


def belongs_to_a_business(user) -> bool:
    """Whether ``user`` is in a business that is not deleted (owner, payer or member), from ``hubs.business.list``
    (called by its name: accounts never imports hubs). A business in its 90 days of recovery holds nobody."""
    business_list = operations.get(BUSINESS_LIST)
    as_account = queries.as_account(user)
    offset = 0
    while True:
        page = business_list(as_account, business_list.input(limit=100, offset=offset))
        if any(row.deletion_requested_at is None for row in page.rows):
            return True
        offset += page.limit
        if offset >= page.total:
            return False
