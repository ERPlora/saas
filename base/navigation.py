"""The panel's menu (round 17, PLAN-SAAS §3.6 point 1): Businesses · Store · Billing · Account.

The SaaS's apps are platform apps (``kind = "platform"``), which declare no ``navigation``
(``live.checks``, PLAN §20.3.3), so the panel's single menu is declared here, with the icons of the
approved mockups (``mockups/saas-panel/``). ``base.session.me`` sends it already translated.

The Store sells, so the app surfaces leave it out (PLAN-SAAS §3.6 point 6): ``Nav`` has no field
for that (``live.meta`` is shared with the Hub), so ``WEB_ONLY`` says it here.
"""

from typing import Any

from django.utils.translation import gettext_lazy as _
from live.meta import Nav

#: The id of the menu's only section: the app that declares it. Its empty label paints no header.
SECTION_ID = "base"

NAVIGATION: list[Nav] = [
    Nav(
        id="businesses", label=_("Businesses"), icon="lucide:store", path="/businesses"
    ),
    Nav(id="store", label=_("Store"), icon="lucide:shopping-bag", path="/store"),
    Nav(id="billing", label=_("Billing"), icon="lucide:receipt", path="/billing"),
    Nav(id="account", label=_("Account"), icon="lucide:circle-user", path="/account"),
]

#: The entries that sell: on the web only (``SessionMenuItem.webOnly`` of packages/ui).
WEB_ONLY: frozenset[str] = frozenset({"store"})


def menu() -> list[dict[str, Any]]:
    """The menu in the shape the shell reads (``SessionMenuSection``), in the active language."""
    return [
        {
            "id": SECTION_ID,
            "label": "",
            "items": [
                {
                    "path": nav.path,
                    "label": str(nav.label),
                    "icon": nav.icon,
                    "webOnly": nav.id in WEB_ONLY,
                }
                for nav in NAVIGATION
            ],
        }
    ]
