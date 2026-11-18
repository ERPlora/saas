"""Who pays for a business: its payer, a plan still charged to an account and a renewal left unpaid."""

from typing import Any

from live.context import OperationContext
from live.operations import AI, operation

from hubs.models import BillingProfile, Hub, HubMember, Subscription
from hubs.queries.access_control import Role, access, account_of
from hubs.schemas.payers import BillingProfileGetIn, BillingProfileOut


def is_payer(member: HubMember) -> bool:
    """Whether ``member``'s account owns its business's payer (``billing_profile``): it pays for the business,
    whatever its role (the owner before a hand-over keeps it until the new one writes its own)."""
    profile = member.hub.billing_profile
    return profile is not None and profile.owner_id == member.user_id


#: Statuses of a Stripe subscription that bill nothing any more (``billing.services.ENDED_STATUSES``).
ENDED_STATUSES = frozenset({"canceled", "incomplete_expired"})


def plans_charged_to(hub_id, user_id):
    """The live Stripe subscription of the business ``hub_id`` when it is still billed to a Stripe customer of a
    payer of the account ``user_id`` (values, or ``OuterRef`` from a subquery)."""
    customers = (
        BillingProfile.objects.filter(owner_id=user_id).exclude(stripe_customer_id="").values("stripe_customer_id")
    )
    return (
        Subscription.objects.filter(hub_id=hub_id, stripe_customer_id__in=customers)
        .exclude(stripe_subscription_id="")
        .exclude(status__in=ENDED_STATUSES)
    )


def paid_until(hub_id):
    """The end of the period already paid of the business's paid plan (a live Stripe subscription), or ``None`` on
    Free: what the mails of a hand-over say (HUBS-F28)."""
    subscription = (
        Subscription.objects.filter(hub_id=hub_id)
        .exclude(stripe_subscription_id="")
        .exclude(status__in=ENDED_STATUSES)
        .first()
    )
    return subscription.current_period_end if subscription is not None else None


def still_pays(member: HubMember) -> bool:
    """Whether ``member``'s account still pays for its business, whatever its role: it owns its payer
    (``is_payer``), or the plan is still charged to the card of one of its payers (after a hand-over the new owner
    says who pays from now on, but a live subscription stays on the old Stripe customer until they keep it with
    their card, ``billing.plan.take_over``, HUBS-F28: until then ``billing.payer_required``). ``business_list``
    annotates the second as ``charged``."""
    if is_payer(member):
        return True
    charged = getattr(member, "charged", None)
    if charged is None:
        charged = plans_charged_to(member.hub_id, member.user_id).exists()
    return charged


def unpaid_of(member: HubMember, subscription: Subscription | None) -> dict[str, Any]:
    """Why the business's renewal is not paid, and since when, as ``member`` sees
    it: the invoice to pay only for its PAYER (after a transfer the owner may not be; the invoice's page
    shows the payer's card), never for a role."""
    if subscription is None or not subscription.unpaid_reason:
        return {"unpaid_reason": None, "unpaid_since": None, "pay_url": None}
    payer = member.hub.billing_profile
    pays = payer is not None and payer.owner_id == member.user_id
    return {
        "unpaid_reason": subscription.unpaid_reason,
        "unpaid_since": subscription.unpaid_since,
        "pay_url": (subscription.unpaid_invoice_url or None) if pays else None,
    }


PAYER_FIELDS = (
    "billing_name",
    "tax_id",
    "billing_address",
    "billing_city",
    "billing_postal_code",
    "billing_country",
    "billing_email",
    "same_as_business",
)


@operation(
    "hubs.billing_profile.get",
    kind="query",
    permission="hubs.view",
    input=BillingProfileGetIn,
    output=BillingProfileOut,
    ai=AI(
        description="Who ERPlora invoices for one business: its payer's name, tax ID and billing address; only its "
        "owner.",
        asks={
            "en": (
                "who are the bar's invoices made out to?",
                "what tax ID is on the salon's bills?",
                "show the billing details of my business",
            ),
            "es": (
                "¿a nombre de quién salen las facturas del bar?",
                "¿qué CIF aparece en las facturas de la peluquería?",
                "datos de facturación del negocio",
            ),
        },
    ),
)
def billing_profile_get(
    ctx: OperationContext, data: BillingProfileGetIn
) -> dict[str, Any]:
    """Who ERPlora invoices for the business (Account → Billing, and the Settings tab): only its owner."""
    member = access(account_of(ctx), data.hub_id, Role.OWNER)
    return payer_of(member.hub, member.user)


def payer_of(hub: Hub, owner) -> dict[str, Any]:
    """The payer of ``hub`` as its ``owner`` edits it: empty when there is none yet, and when it is
    another account's (it keeps paying; its data is not the new owner's to read)."""
    profile = hub.billing_profile
    if profile is None or profile.owner_id != owner.pk:
        return {
            "hub_id": hub.id,
            **{field: "" for field in PAYER_FIELDS},
            "same_as_business": False,
            "paid_by_another_account": profile is not None,
        }
    return {
        "hub_id": hub.id,
        **{field: getattr(profile, field) for field in PAYER_FIELDS},
        "paid_by_another_account": False,
    }
