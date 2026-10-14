"""The Checkout Session vocabulary of billing: its ``ui_mode`` and what a session pays for.

Ported from ERPlora/saas ``apps/core/stripe_checkout.py`` (origin/develop).

``ui_mode`` (saas#1565): Stripe renamed ``embedded`` to ``embedded_page`` and the retired spelling killed
both embedded checkouts at once. The value lives here, and ``accepted_ui_modes`` reads the enum of the
INSTALLED SDK, so the test that compares them turns red on the SDK bump, before a customer meets it.

``kind`` (saas#2539): every Checkout Session carries ``metadata.kind``. The SaaS has one webhook route
(PLAN-SAAS §4), which tells a plan payment from a module purchase and ignores any other session of the
account (the old SaaS's assistant shares it until the cut-over).
"""

import re
from collections.abc import Mapping
from enum import StrEnum

#: ``ui_mode`` of a Checkout Session rendered inside our page (Embedded Checkout in a modal).
EMBEDDED_UI_MODE = "embedded_page"

#: Metadata key every Checkout Session of ERPlora carries to say what it pays for.
KIND_METADATA_KEY = "kind"

_QUOTED = re.compile(r"'([^']+)'")


def _ui_mode_annotation() -> object | None:
    """The raw ``ui_mode`` annotation of the installed SDK (read by the gateway, the one importer of
    ``stripe``), or ``None``."""
    from billing import stripe_service

    return stripe_service.checkout_ui_mode_annotation()


def accepted_ui_modes() -> frozenset[str]:
    """Every ``ui_mode`` value the installed Stripe SDK declares for a session.

    The SDK annotates it as ``NotRequired["Literal['elements', 'embedded_page', …]|str"]``: a forward
    reference whose text carries the values. Raises ``RuntimeError`` when the SDK no longer exposes it:
    answering «none found» would let a wrong ``ui_mode`` sail through the guard test.
    """
    annotation = _ui_mode_annotation()
    if annotation is None:
        raise RuntimeError(
            "The installed Stripe SDK does not expose the Checkout Session `ui_mode` enum "
            "(stripe.params.checkout.SessionCreateParams): point this helper at its new place."
        )
    values = set(_QUOTED.findall(repr(annotation)))
    if not values:
        raise RuntimeError(f"No `ui_mode` value could be read out of {annotation!r}.")
    return frozenset(values)


class CheckoutKind(StrEnum):
    """What a Checkout Session pays for."""

    HUB_PLAN = "hub_plan"
    MODULE_PURCHASE = "module_purchase"
    #: Not ERPlora's billing of a business: ignored by the webhook.
    UNKNOWN = "unknown"


def checkout_session_kind(metadata: Mapping | None) -> CheckoutKind:
    """Classify a Checkout Session by its metadata; ``UNKNOWN`` is not ours.

    The ``kind`` tag wins. A session opened before the tag existed (Stripe keeps one open up to 24 h) is
    recognised by its shape: a module purchase always carried ``module_id``, a plan payment never did.
    """
    if not metadata:
        return CheckoutKind.UNKNOWN
    tag = metadata.get(KIND_METADATA_KEY)
    if tag:
        try:
            return CheckoutKind(tag)
        except ValueError:
            return CheckoutKind.UNKNOWN
    if metadata.get("module_id"):
        return CheckoutKind.MODULE_PURCHASE
    if metadata.get("hub_id"):
        return CheckoutKind.HUB_PLAN
    return CheckoutKind.UNKNOWN
