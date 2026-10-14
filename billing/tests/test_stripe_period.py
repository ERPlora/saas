"""The billing period of a Stripe subscription, whatever API version shaped it (``billing.stripe_period``).

Ported from ERPlora/saas ``apps/core/stripe_period.py`` and the tests that pinned it
(``hubs/subscriptions/tests/test_stripe_status_reads_item_period.py`` and
``hubs/main/tests/test_live_period_read_from_subscription_item.py``, origin/develop; saas#2328, #2344).
Since ``2025-03-31.basil`` the period lives on ``items.data[]``, not on the subscription root; an old
event still carries it at the root. Both shapes yield the same period; the root wins when it has it.
The gateway hands billing plain dicts (``billing.stripe_service``), so the reader takes a dict.
"""

from billing.stripe_period import subscription_period

START = 1_790_000_000 - 2_592_000
END = 1_790_000_000


def item(**fields):
    return {"id": "si_1", "object": "subscription_item", **fields}


def test_the_current_api_keeps_the_period_on_the_first_item():
    live = {
        "id": "sub_1",
        "items": {"data": [item(current_period_start=START, current_period_end=END)]},
    }

    assert subscription_period(live) == (START, END)


def test_an_old_event_keeps_it_at_the_root():
    legacy = {
        "id": "sub_1",
        "current_period_start": START,
        "current_period_end": END,
        "items": {"data": []},
    }

    assert subscription_period(legacy) == (START, END)


def test_the_root_wins_and_each_missing_half_comes_from_the_item():
    mixed = {
        "id": "sub_1",
        "current_period_start": START,
        "items": {"data": [item(current_period_start=1, current_period_end=END)]},
    }

    assert subscription_period(mixed) == (START, END)


def test_no_period_anywhere_is_none_not_an_error():
    assert subscription_period({"id": "sub_1"}) == (None, None)
    assert subscription_period({"id": "sub_1", "items": {"data": []}}) == (None, None)
    assert subscription_period({"id": "sub_1", "items": None}) == (None, None)


def test_a_zero_is_no_period():
    assert subscription_period(
        {"current_period_start": 0, "current_period_end": 0}
    ) == (None, None)
