"""The billing period of a Stripe subscription, whatever API version shaped it (saas#2328).

Ported from ERPlora/saas ``apps/core/stripe_period.py`` (origin/develop). Since ``2025-03-31.basil``
``current_period_start``/``current_period_end`` live on ``items.data[]``, not on the subscription root;
an event of an older endpoint still carries them at the root. Both shapes yield the same period. The
gateway (``billing.stripe_service``) hands billing plain dicts, so this reads a dict.
"""


def _first_item(subscription: dict) -> dict | None:
    items = subscription.get("items")
    data = (items.get("data") or []) if isinstance(items, dict) else []
    return data[0] if data else None


def subscription_period(subscription: dict) -> tuple[int | None, int | None]:
    """``(current_period_start, current_period_end)`` as unix timestamps, ``None`` when absent.

    The root wins; each half missing there is taken from the first subscription item.
    """
    start = subscription.get("current_period_start")
    end = subscription.get("current_period_end")
    if not (start and end):
        item = _first_item(subscription)
        if item is not None:
            start = start or item.get("current_period_start")
            end = end or item.get("current_period_end")
    return start or None, end or None
