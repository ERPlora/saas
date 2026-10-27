"""The panel's menu (round 17, PLAN-SAAS §3.6 point 1): Businesses · Store · Billing · Account.

The SaaS's apps are platform apps (``kind = "platform"``), which declare no ``navigation``
(``live.checks``, PLAN §20.3.3), so the panel's single menu is declared here, with the icons of the
approved mockups (``mockups/saas-panel/``). ``base.session.me`` sends it already translated.

The Store sells, so the app surfaces leave it out (PLAN-SAAS §3.6 point 6): ``Nav`` has no field
for that (``live.meta`` is shared with the Hub), so ``WEB_ONLY`` says it here.

The panel's addresses are named here once (``PANEL`` and the pages under it): the menu, the 301s of the old ones
(``config/urls.py``, ``hubs.redirects``, ``accounts.redirects``) and every link the server writes to the panel
(mails, Stripe's return) build on them.
"""

from typing import Any

from django.utils.translation import gettext_lazy as _
from live.meta import Nav

#: The id of the menu's only section: the app that declares it. Its empty label paints no header.
SECTION_ID = "base"

#: Where the panel lives: every page shown with this menu, as the old product's ``apps/dashboard/``
#: (FIX-SAAS-PANEL-UNDER-DASHBOARD-PREFIX). The launcher, the sign-in's pages and the invitations stay at the root.
PANEL = "/dashboard"
BUSINESSES = f"{PANEL}/businesses"
STORE = f"{PANEL}/store"
BILLING = f"{PANEL}/billing"
ACCOUNT = f"{PANEL}/account"
REPORT_PROBLEM = f"{PANEL}/report-a-problem"

NAVIGATION: list[Nav] = [
    Nav(id="businesses", label=_("Businesses"), icon="lucide:store", path=BUSINESSES),
    Nav(id="store", label=_("Store"), icon="lucide:shopping-bag", path=STORE),
    Nav(id="billing", label=_("Billing"), icon="lucide:receipt", path=BILLING),
    Nav(id="account", label=_("Account"), icon="lucide:circle-user", path=ACCOUNT),
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
