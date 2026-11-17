"""The pass back from a business to erplora.com (``accounts/hub_pass.py``)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from live import operations

from accounts import queries
from accounts.models import AuthExchangeCode
from accounts.services.account_businesses import BUSINESS_LIST


#: The audience of the row that spends a pass: never a jump's, so ``redeem_code`` finds no pass.
HUB_PASS_AUDIENCE = "hub-pass"


def hub_pass_member(user_id: str, hub_slug: str):
    """``(account, id of the business)`` if the account ``user_id`` may follow a pass of ``hub_slug``; else ``None``.

    Only an active account, never one of the platform's staff (a pass carries no second factor), that is
    a member of that business as ``hubs.business.list`` sees it (an accepted invitation; called by its name: accounts
    never imports hubs)."""
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None or not user.is_active or user.is_staff or user.is_superuser:
        return None
    business_list = operations.get(BUSINESS_LIST)
    as_account = queries.as_account(user)
    offset = 0
    while True:
        page = business_list(as_account, business_list.input(search=hub_slug, limit=100, offset=offset))
        for row in page.rows:
            if row.slug == hub_slug:
                return user, row.id
        offset += page.limit
        if offset >= page.total:
            return None


def spend_hub_pass(user, hub_slug: str, nonce: str, lifetime: timedelta) -> bool:
    """Spend the pass ``nonce``; whether it was not spent before.

    One row per pass, stored used, with the nonce's SHA-256 under its own audience (no jump code shares it): the unique
    hash refuses a second one, however many browsers follow the pass at once. The row outlives the pass twice over
    (``purge_expired_sign_in_leftovers`` deletes it past ``expires_at``): a pass the Hub dated a little ahead of this
    clock still meets it."""
    now = timezone.now()
    try:
        with transaction.atomic():
            AuthExchangeCode.objects.create(
                code_hash=AuthExchangeCode.hash_code(f"{HUB_PASS_AUDIENCE}:{nonce}"),
                user=user,
                audience=HUB_PASS_AUDIENCE,
                hub_slug=hub_slug,
                created_at=now,
                used_at=now,
                expires_at=now + 2 * lifetime,
            )
    except IntegrityError:
        return False
    return True
