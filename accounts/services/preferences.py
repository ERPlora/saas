"""Account → Preferences: the theme, its transparency effects, the language and the alerts of the account's
businesses."""

from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from accounts import events, queries
from accounts.models import UserPreferences
from accounts.schemas import PreferencesOut, PreferencesUpdateIn


@operation(
    "accounts.preferences.update",
    kind="command",
    permission="accounts.manage",
    input=PreferencesUpdateIn,
    output=PreferencesOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description="Changes the account's theme, transparency effects, language or alerts of its businesses.",
        asks={
            "en": (
                "switch the panel to dark mode",
                "change my language to English",
                "I want the light theme back",
                "turn off the alerts from my businesses",
                "turn off the transparency effects",
            ),
            "es": (
                "ponme el modo oscuro",
                "cámbiame el idioma a inglés",
                "desactiva los avisos",
                "no quiero recibir avisos de los negocios",
                "quita los efectos de transparencia",
            ),
        },
    ),
)
def preferences_update(ctx: OperationContext, data: PreferencesUpdateIn) -> dict:
    """Change what was sent and nothing else. The language is the account's own (``User.language``); the
    rest lives in ``UserPreferences``, whose row is born with the first change."""
    user = queries.account_of(ctx)
    changes = data.model_dump(exclude_none=True)
    language = changes.pop("language", None)
    if language is not None:
        # Read again: ``ctx.actor`` is the request's account, which a try a cut rolled back changed in memory.
        user.refresh_from_db(fields=["language"])
        if language != user.language:
            user.language = language
            user.save(update_fields=["language"])
    if changes:
        preferences, _ = UserPreferences.objects.select_for_update().get_or_create(user=user)
        for field, value in changes.items():
            setattr(preferences, field, value)
        preferences.save()
    record_event(ctx, events.PREFERENCES_UPDATED)
    return queries.preferences_of(user)
