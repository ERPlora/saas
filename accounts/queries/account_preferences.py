"""Account → Preferences: what the account chose, and whether it gets the business notices."""

from typing import Any

from live.context import OperationContext
from live.operations import AI, operation

from accounts.models import UserPreferences
from accounts.queries.account_lookup import account_of
from accounts.schemas import PreferencesGetIn, PreferencesOut


def preferences_of(user) -> dict[str, Any]:
    """What the account chose, or the defaults when it never changed anything (no row is written)."""
    preferences = UserPreferences.objects.filter(user=user).first() or UserPreferences(user=user)
    return {
        "theme_mode": preferences.theme_mode,
        "transparency": preferences.transparency,
        "language": user.language,
        "hub_alerts": preferences.hub_alerts,
    }


def receives_business_notices(user) -> bool:
    """Whether ``user`` gets the business notices (Account → Preferences, ``hub_alerts``; on until turned off): the
    mail that a business is ready (``hubs.emails.send_ready``). The mails that keep the account safe or its businesses
    running ask nobody."""
    preferences = UserPreferences.objects.filter(user=user).values_list("hub_alerts", flat=True).first()
    return True if preferences is None else preferences


@operation(
    "accounts.preferences.get",
    kind="query",
    permission="accounts.view",
    input=PreferencesGetIn,
    output=PreferencesOut,
    ai=AI(
        description="The account's preferences: theme, transparency effects, language and alerts of its businesses.",
        asks={
            "en": ("what language is my account in?", "do I get alerts from my businesses?", "show my preferences"),
            "es": (
                "¿en qué idioma tengo la cuenta?",
                "¿qué preferencias tengo?",
                "¿qué tema tengo puesto?",
                "¿tengo activados los avisos de mis negocios?",
            ),
        },
    ),
)
def preferences_get(ctx: OperationContext, data: PreferencesGetIn) -> dict[str, Any]:
    """Account → Preferences of the signed-in account."""
    return preferences_of(account_of(ctx))
