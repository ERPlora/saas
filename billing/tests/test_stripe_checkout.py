"""The Checkout Session vocabulary of billing (``billing.stripe_checkout``): its ``ui_mode`` and its kind.

Ported from ERPlora/saas ``apps/core/stripe_checkout.py`` (origin/develop) with its guards:

- saas#1565: Stripe renamed ``embedded`` to ``embedded_page`` and both embedded checkouts died at once. The
  value lives in one place and a test compares it with the enum of the INSTALLED SDK, so an SDK bump that
  drops it turns red before a customer meets the error.
- saas#2539 (``dashboard/billing/tests/test_checkout_session_routing.py``): every Checkout Session carries
  ``metadata.kind``. The old SaaS had four webhook routes, each receiving the others' sessions; the new one
  has ONE (PLAN-SAAS §4), which still must tell a plan payment from a module purchase and ignore what is
  not ours (the assistant's sessions of the old SaaS share the Stripe account until the cut-over).
"""

import pytest

from billing.stripe_checkout import (
    EMBEDDED_UI_MODE,
    KIND_METADATA_KEY,
    CheckoutKind,
    accepted_ui_modes,
    checkout_session_kind,
)


def test_the_embedded_ui_mode_is_one_the_installed_sdk_accepts():
    assert EMBEDDED_UI_MODE == "embedded_page"
    assert EMBEDDED_UI_MODE in accepted_ui_modes()


def test_the_retired_spelling_is_not_accepted_any_more():
    assert "embedded" not in accepted_ui_modes()


def test_reading_the_enum_fails_loudly_when_the_sdk_hides_it(monkeypatch):
    from billing import stripe_checkout

    monkeypatch.setattr(stripe_checkout, "_ui_mode_annotation", lambda: None)

    with pytest.raises(RuntimeError):
        accepted_ui_modes()


@pytest.mark.parametrize(
    "metadata, kind",
    [
        ({KIND_METADATA_KEY: "hub_plan", "hub_id": "h"}, CheckoutKind.HUB_PLAN),
        (
            {KIND_METADATA_KEY: "module_purchase", "hub_id": "h"},
            CheckoutKind.MODULE_PURCHASE,
        ),
        # The old SaaS's assistant shares the account until the cut-over: not ours.
        (
            {KIND_METADATA_KEY: "assistant_subscription", "hub_id": "h"},
            CheckoutKind.UNKNOWN,
        ),
        ({KIND_METADATA_KEY: "something_new"}, CheckoutKind.UNKNOWN),
        # Sessions opened before the tag existed (Stripe keeps one open up to 24 h): by their shape.
        ({"module_id": "m", "hub_id": "h"}, CheckoutKind.MODULE_PURCHASE),
        ({"hub_id": "h"}, CheckoutKind.HUB_PLAN),
        ({}, CheckoutKind.UNKNOWN),
        (None, CheckoutKind.UNKNOWN),
    ],
)
def test_a_session_is_classified_by_its_metadata(metadata, kind):
    assert checkout_session_kind(metadata) is kind


def test_the_tag_wins_over_the_legacy_shape():
    assert (
        checkout_session_kind({KIND_METADATA_KEY: "hub_plan", "module_id": "m"})
        is CheckoutKind.HUB_PLAN
    )
