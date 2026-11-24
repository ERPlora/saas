"""The Stripe prices of the paid plans, as the admin pastes them in every environment that sells: the Store sells a
plan only with the billings it has a price for. Seeded before the e2e run, removed after it.

``uv run python tests/e2e/plan_prices_seed.py seed|clear`` from the repo, against the local database of ``.env``.
Only a plan without a price gets one, marked ``price_e2e_``, and ``clear`` empties only those: a price somebody
pasted in the local database stays. A plan without an annual price (the internal one) gets no annual Stripe price.
"""

import os
import sys
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[2]
MARK = "price_e2e_"


def main(action: str) -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from hubs.models import Plan

    Plan.objects.filter(stripe_price_id__startswith=MARK).update(stripe_price_id="")
    Plan.objects.filter(stripe_price_id_annual__startswith=MARK).update(stripe_price_id_annual="")
    if action == "seed":
        paid = Plan.objects.filter(price_monthly__gt=0)
        for plan in paid.filter(stripe_price_id=""):
            Plan.objects.filter(pk=plan.pk).update(stripe_price_id=f"{MARK}{plan.slug}_month")
        for plan in paid.filter(price_annual__gt=0, stripe_price_id_annual=""):
            Plan.objects.filter(pk=plan.pk).update(stripe_price_id_annual=f"{MARK}{plan.slug}_year")
    print(f"{action}: the Stripe prices of the paid plans")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: plan_prices_seed.py seed|clear")
    main(sys.argv[1])
