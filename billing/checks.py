"""System checks of billing (deploy): live money only through a RESTRICTED Stripe key (PLAN-SAAS §4).

The account's live secret key (``sk_live_``) can do everything a thief would want; a restricted one
(``rk_live_``) only what the SaaS needs. The gateway refuses the secret one too
(``billing.stripe_service.key_mode``); this makes the deploy fail before a task starts with it.
"""

from django.conf import settings
from django.core import checks


@checks.register(checks.Tags.security, deploy=True)
def check_stripe_key(app_configs=None, **kwargs):
    key = getattr(settings, "STRIPE_SECRET_KEY", "") or ""
    if key.startswith("sk_live_"):
        return [
            checks.Error(
                "STRIPE_SECRET_KEY is the Stripe account's live SECRET key.",
                hint="Use a restricted live key (rk_live_…) with only the permissions the SaaS needs.",
                id="billing.E001",
            )
        ]
    return []
