"""The payer's billing details of a business."""

from functools import partial

from django.db import transaction
from django.utils.translation import gettext as _
from live.context import OperationContext
from live.errors import InvalidPayload
from live.operations import AI, operation
from live.outbox import record_event

from base.refusals import fields_refused
from hubs import events
from hubs.models import BillingProfile
from hubs.queries import access_control, payers
from hubs.queries.access_control import Role
from hubs.schemas import BillingProfileIn, BillingProfileOut, postal_code_problem


@operation(
    "hubs.billing_profile.update",
    kind="command",
    permission="hubs.manage",
    input=BillingProfileIn,
    output=BillingProfileOut,
    ai=AI(
        description="Changes who ERPlora invoices for a business: name, tax ID, billing address and email; only its "
                    "owner.",
        asks={
            "en": (
                "put the bar's invoices in the name of Manolo SL",
                "change the tax ID on my invoices to B12345678",
                "update the billing address of the salon",
            ),
            "es": (
                "pon las facturas del bar a nombre de Manolo SL",
                "cambia el CIF de facturación a B12345678",
                "la dirección fiscal de la peluquería ha cambiado",
            ),
        },
    ),
)
def billing_profile_update(ctx: OperationContext, data: BillingProfileIn) -> dict:
    """The owner says who ERPlora invoices for the business. «Use the business's data» copies its name
    and country into the payer: a copy, not a sync.

    The tax ID goes through billing's VAT door (``billing.services.validate_vat_for_profile``): written
    as ERPlora invoices it and asked to VIES, whose verdict is logged; a malformed one is the field's 422,
    one VIES does not confirm is kept as identification (it buys no reverse charge)."""
    from billing import vat
    from billing.services import MalformedVatNumber, retax_payer, validate_vat_for_profile

    member = access_control.access(access_control.account_of(ctx), data.hub_id, Role.OWNER, lock=True)
    hub = member.hub
    values = data.model_dump(exclude={"hub_id"})
    if data.same_as_business:
        values["billing_name"] = hub.name
        values["billing_country"] = hub.country
    if values["billing_country"] and not vat.sells_to(values["billing_country"]):
        # Said on top as well: with «use the business's data» the country field is not on screen.
        reason = _("For now ERPlora only invoices payers in Spain.")
        raise InvalidPayload(reason, fields={"billing_country": reason})
    problem = postal_code_problem(values["billing_country"], values["billing_postal_code"])
    if problem:
        raise fields_refused({"billing_postal_code": problem})
    try:
        # Without the payer's country yet (it may wait for the first checkout), read it in the business's.
        country = values["billing_country"] or hub.country
        values["tax_id"] = validate_vat_for_profile(country, values["tax_id"]).vat_number
    except MalformedVatNumber:
        raise fields_refused({"tax_id": _("Enter a valid tax ID for the country of the payer.")}) from None
    profile = hub.billing_profile
    if profile is None or profile.owner_id != member.user_id:
        # A payer is somebody's: the one another account set up (the owner before a transfer) keeps
        # its data and its other businesses; this business gets a payer of its current owner.
        profile = BillingProfile.objects.create(owner=member.user)
        hub.billing_profile = profile
        hub.save(update_fields=["billing_profile", "updated_at"])
    for field, value in values.items():
        setattr(profile, field, value)
    profile.save()
    record_event(ctx, events.BILLING_PROFILE_UPDATED, {"hub_id": str(hub.id)})
    # The live subscription takes the rate of the new place from its next invoice (BILLING-F02).
    transaction.on_commit(partial(retax_payer, profile.pk))
    return payers.payer_of(hub, member.user)
