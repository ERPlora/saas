"""Account → Profile: the account's first and last name."""

from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from accounts import events, queries
from accounts.schemas import ProfileOut, ProfileUpdateIn


@operation(
    "accounts.profile.update",
    kind="command",
    permission="accounts.manage",
    input=ProfileUpdateIn,
    output=ProfileOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Changes the account's first and last name.",
        asks={
            "en": ("change my name to Lena Ruiz", "my surname is wrong, it's García", "update my last name"),
            "es": ("cambia mi nombre a Lena Ruiz", "mi apellido está mal, es García", "ponme de apellido Martínez"),
        },
    ),
)
def profile_update(ctx: OperationContext, data: ProfileUpdateIn) -> dict:
    """The names, trimmed: the first one is required, an empty last one clears it. The sign-in email
    has its own door, ``accounts.email.change``."""
    user = queries.account_of(ctx)
    user.first_name = data.first_name.strip()
    user.last_name = data.last_name.strip()
    user.save(update_fields=["first_name", "last_name"])
    record_event(ctx, events.PROFILE_UPDATED)
    return queries.profile_of(user, ctx.request)
