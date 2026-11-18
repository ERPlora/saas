"""Creating a business: its address, its time zone and its Free plan."""

from datetime import timedelta
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, operation
from live.outbox import record_event
from live.slugs import (
    HUB_SLUG_MAX_LENGTH,
    INVALID_FORMAT,
    PUNYCODE,
    RESERVED,
    TOO_LONG,
    TOO_SHORT,
    hub_slug_min_length,
    validate_hub_slug,
)

from accounts.services import hub_jump
from base.refusals import fields_refused
from hubs import events
from hubs.models import BillingProfile, Hub, HubMember, Subscription
from hubs.queries import access_control, addresses, businesses, plan_catalog, signup, taxonomy
from hubs.queries.access_control import Role
from hubs.schemas.businesses import BusinessDetailOut
from hubs.schemas.signup import BusinessCreateIn
from hubs.services.hub_push import Call, push_after_commit
from hubs.services.subscription_sync import sync_plan_modules


#: The time zone a business starts with, by country (the capital's); the owner may change it.
TIME_ZONES = {
    "AT": "Europe/Vienna",
    "BE": "Europe/Brussels",
    "BG": "Europe/Sofia",
    "HR": "Europe/Zagreb",
    "CY": "Asia/Nicosia",
    "CZ": "Europe/Prague",
    "DK": "Europe/Copenhagen",
    "EE": "Europe/Tallinn",
    "FI": "Europe/Helsinki",
    "FR": "Europe/Paris",
    "DE": "Europe/Berlin",
    "GR": "Europe/Athens",
    "HU": "Europe/Budapest",
    "IE": "Europe/Dublin",
    "IT": "Europe/Rome",
    "LV": "Europe/Riga",
    "LT": "Europe/Vilnius",
    "LU": "Europe/Luxembourg",
    "MT": "Europe/Malta",
    "NL": "Europe/Amsterdam",
    "PL": "Europe/Warsaw",
    "PT": "Europe/Lisbon",
    "RO": "Europe/Bucharest",
    "SK": "Europe/Bratislava",
    "SI": "Europe/Ljubljana",
    "ES": "Europe/Madrid",
    "SE": "Europe/Stockholm",
}
#: A derived address tried this many times when two sign-ups race for it.
SLUG_ATTEMPTS = 20


@operation(
    "hubs.business.create",
    kind="command",
    permission="hubs.manage",
    input=BusinessCreateIn,
    output=BusinessDetailOut,
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut).
    ai=AI(
        description=(
            "Creates a business on the Free plan with its address. An account has one free business, and whether one "
            "more fits is for this tool to say: call it, never refuse on your own. With no room it answers "
            "hubs.free_hub_limit: Change the plan of that business to create another one."
        ),
        risk="high",
        # Its card only comes if the write would run: it has nothing more to show.
        preview={"operation": "hubs.business.create_check", "fields": []},
        asks={
            "en": (
                "create another business in Valencia",
                "open a new shop called Café Luna",
                "set up my restaurant on ERPlora",
            ),
            "es": (
                "créame otro negocio en Valencia",
                "abre un negocio nuevo que se llame Café Luna",
                "quiero dar de alta mi peluquería",
            ),
        },
    ),
)
def business_create(ctx: OperationContext, data: BusinessCreateIn) -> dict:
    """The sign-up: in one transaction the payer, the business, its owner and its Free subscription (with
    the trial of ``plan_catalog.trial_plan`` when a plan carries one); after the COMMIT, the Hub.

    One free business per account (``FREE_HUBS_PER_ACCOUNT``); a name never blocks it.
    """
    user = access_control.account_of(ctx)
    plan = signup.plan_of_a_new_business()
    signup.refuse_staff(user)
    check_free_quota(user)
    now = timezone.now()
    profile = BillingProfile.objects.create(
        owner=user, billing_email=user.email, billing_country=data.country
    )
    hub = _create_hub(
        data, user, profile, taxonomy.business_type_for(data.business_type), now
    )
    owner = HubMember.objects.create(
        hub=hub, user=user, role=Role.OWNER, joined_at=now, accepted_at=now
    )
    _subscribe_to_free(hub, plan, now)
    record_event(ctx, events.BUSINESS_CREATED, {"id": str(hub.id)})
    push_after_commit(hub.id)
    return businesses.business_detail(owner)


def check_free_quota(user, excluding: UUID | None = None) -> None:
    """One more Free business fits ``user``'s quota (``FREE_HUBS_PER_ACCOUNT``).

    The account's row is locked first: two requests of one account (two tabs, a double click) are
    serialised here, so the second counts the business the first is creating.
    """
    get_user_model().objects.select_for_update().filter(pk=user.pk).first()
    signup.refuse_full_free_quota(user, excluding=excluding)


def _create_hub(
    data: BusinessCreateIn, user, profile: BillingProfile, business_type, now
) -> Hub:
    fields = {
        "name": data.name,
        "country": data.country,
        "timezone": TIME_ZONES.get(data.country, "Europe/Madrid"),
        "language": user.language,
        "business_type": business_type,
        "billing_profile": profile,
        "status": Hub.Status.PREPARING,
        "provision_requested_at": now,
        "pending_hub_call": Call.PUT,
    }
    if data.slug is not None:
        slug = _chosen_slug(data.slug)
        try:
            with transaction.atomic():
                return Hub.objects.create(slug=slug, **fields)
        except IntegrityError:
            raise _slug_taken() from None
    for _attempt in range(SLUG_ATTEMPTS):
        try:
            with transaction.atomic():
                return Hub.objects.create(slug=addresses.free_slug(data.name), **fields)
        except IntegrityError:
            continue  # another sign-up took it between the read and the write: the next one is free
    raise _slug_taken()


#: Why a chosen address is refused, by the code of ``live.slugs.validate_hub_slug``.
SLUG_PROBLEMS = {
    INVALID_FORMAT: gettext_lazy(
        "Use only lowercase letters, digits and hyphens, without a hyphen at the start or the end."
    ),
    TOO_SHORT: gettext_lazy("Use at least %(min)d characters."),
    TOO_LONG: gettext_lazy("Use at most %(max)d characters."),
    PUNYCODE: gettext_lazy("The address cannot start with “xn--”."),
}


def _chosen_slug(slug: str, excluding: UUID | None = None) -> str:
    try:
        validate_hub_slug(slug)
    except ValueError as refused:
        code = str(refused)
        if code == RESERVED:
            raise Conflict(_("This address is reserved. Choose another one."), code="hubs.slug_reserved") from None
        message = str(SLUG_PROBLEMS.get(code, SLUG_PROBLEMS[INVALID_FORMAT])) % {
            "min": hub_slug_min_length(),
            "max": HUB_SLUG_MAX_LENGTH,
        }
        raise fields_refused({"slug": message}) from None
    if slug == hub_jump.PLATFORM_HOST_SLUG:
        raise Conflict(_("This address is reserved. Choose another one."), code="hubs.slug_reserved")
    if addresses.slug_taken(slug, excluding=excluding):
        raise _slug_taken()
    return slug


def _slug_taken() -> Conflict:
    return Conflict(
        _("This address is taken. Choose another one."), code="hubs.slug_taken"
    )


def _subscribe_to_free(hub: Hub, plan, now) -> Subscription:
    trial = plan_catalog.trial_plan()
    if trial is None:
        subscription = Subscription.objects.create(
            hub=hub,
            plan=plan,
            status=Subscription.Status.ACTIVE,
            current_period_start=now,
        )
    else:
        subscription = Subscription.objects.create(
            hub=hub,
            plan=plan,
            trial_plan=trial,
            status=Subscription.Status.TRIALING,
            current_period_start=now,
            trial_start=now,
            trial_end=now + timedelta(days=trial.trial_period_days),
        )
    sync_plan_modules(subscription, now)
    return subscription
