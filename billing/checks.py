"""Deploy checks: restricted live keys only, and both keys must match STRIPE_EXPECTED_MODE."""

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
    expected_mode = settings.STRIPE_EXPECTED_MODE
    publishable = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or ""
    if expected_mode == "test" and (
        stripe_key_mode(key) is StripeKeyMode.LIVE or publishable.startswith("pk_live_")
    ):
        errors.append(
            checks.Error(
                "A live Stripe key is configured while STRIPE_EXPECTED_MODE=test.",
                hint="Use Stripe's test mode only: rk_test_…/sk_test_… and pk_test_….",
                id="billing.E002",
            )
        )
    if expected_mode == "live" and (
        stripe_key_mode(key) is StripeKeyMode.TEST or publishable.startswith("pk_test_")
    ):
        errors.append(
            checks.Error(
                "A test Stripe key is configured while STRIPE_EXPECTED_MODE=live.",
                hint="Production charges real money only: the restricted rk_live_… key and pk_live_….",
                id="billing.E003",
            )
        )
    return errors
