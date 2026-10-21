"""System checks of billing (deploy): live money only through a RESTRICTED Stripe key (PLAN-SAAS §4), and
only in prod.

The account's live secret key (``sk_live_``) can do everything a thief would want; a restricted one
(``rk_live_``) only what the SaaS needs. The gateway refuses the secret one too
(``billing.stripe_service.key_mode``); this makes the deploy fail before a task starts with it.

Outside prod (``ERPLORA_ENVIRONMENT=pre``, plan 2026-10-14-entorno-pre) Stripe runs in test mode only:
whoever pushes to the pre branch runs code with pre's secrets, so any live key there (secret, restricted
or publishable) fails the deploy too (``billing.E002``), and the gateway refuses it as well.

Production (DEBUG off) is the other way round: a test key there would sell paid plans for test cards, so it
fails the deploy (``billing.E003``) and the gateway refuses it. Development runs as prod with DEBUG on and keeps
its test keys.
"""

from django.conf import settings
from django.core import checks

from billing.stripe_keys import StripeKeyMode, stripe_key_mode


@checks.register(checks.Tags.security, deploy=True)
def check_stripe_key(app_configs=None, **kwargs):
    key = getattr(settings, "STRIPE_SECRET_KEY", "") or ""
    errors = []
    if key.startswith("sk_live_"):
        errors.append(
            checks.Error(
                "STRIPE_SECRET_KEY is the Stripe account's live SECRET key.",
                hint="Use a restricted live key (rk_live_…) with only the permissions the SaaS needs.",
                id="billing.E001",
            )
        )
    environment = settings.ERPLORA_ENVIRONMENT
    publishable = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or ""
    if environment != "prod" and (
        stripe_key_mode(key) is StripeKeyMode.LIVE or publishable.startswith("pk_live_")
    ):
        errors.append(
            checks.Error(
                f"A live Stripe key is configured in the {environment} environment.",
                hint="Outside prod use Stripe's test mode only: rk_test_…/sk_test_… and pk_test_….",
                id="billing.E002",
            )
        )
    if not settings.STRIPE_TEST_KEYS_ALLOWED and (
        stripe_key_mode(key) is StripeKeyMode.TEST or publishable.startswith("pk_test_")
    ):
        errors.append(
            checks.Error(
                "A test Stripe key is configured in production.",
                hint="Production charges real money only: the restricted rk_live_… key and pk_live_….",
                id="billing.E003",
            )
        )
    return errors
