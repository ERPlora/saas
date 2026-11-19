"""Account → Profile → «Download my data» (GDPR art. 20)."""

from typing import Any

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.utils import timezone
from live.context import OperationContext
from live.operations import INTERNAL, operation

from accounts.models import ApiKey, ProfilePhoto
from accounts.queries.account_lookup import account_of
from accounts.queries.account_preferences import preferences_of
from accounts.queries.account_sessions import live_sessions, session_row
from accounts.queries.ways_in import email_is_proven
from accounts.schemas import DataExportIn, DataExportOut


#: The other apps' reads the file carries, called by their name: accounts never imports hubs nor billing.
BUSINESS_LIST = "hubs.business.list"
INVOICE_LIST = "billing.invoice.list"
INVOICE_GET = "billing.invoice.get"
#: The largest page each of those reads gives.
EXPORT_PAGE = 100


def _every_row(ctx: OperationContext, name: str, **params) -> list:
    """Every row of the paged read ``name`` (``rows``, ``total``, ``limit``), page after page."""
    from live import operations

    read = operations.get(name)
    rows: list = []
    while True:
        page = read(ctx, read.input(limit=EXPORT_PAGE, offset=len(rows), **params))
        rows.extend(page.rows)
        if not page.rows or len(rows) >= page.total:
            return rows


def _export_account(user) -> dict[str, Any]:
    return {
        "id": user.pk,
        "email": user.email,
        "email_verified": email_is_proven(user, user.email),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "language": user.language,
        "has_password": user.has_usable_password(),
        "date_joined": user.date_joined,
        "last_login": user.last_login,
        "terms": {
            "accepted_at": user.terms_accepted_at,
            "terms_version": user.terms_version,
            "privacy_version": user.privacy_version,
        },
    }


def _export_sessions(user) -> list[dict[str, Any]]:
    from allauth.usersessions.models import UserSession

    order = [pk for pk, _ in live_sessions(user)]
    found = UserSession.objects.in_bulk(order)
    return [session_row(found[pk], None) for pk in order if pk in found]


@operation(
    "accounts.data.export",
    kind="query",
    permission="accounts.view",
    input=DataExportIn,
    output=DataExportOut,
    ai=INTERNAL,  # file
)
def data_export(ctx: OperationContext, data: DataExportIn) -> dict[str, Any]:
    """Account → Profile → «Download my data»: everything the account is and did here, in one JSON document (GDPR
    art. 20). Only the caller's: each part is read for its account, and the businesses and invoices through the
    operations that already keep them to it (``hubs.business.list``, ``billing.invoice.list``/``.get``)."""
    from live import operations

    user = account_of(ctx)
    photo = ProfilePhoto.objects.filter(user=user).first()
    invoice_get = operations.get(INVOICE_GET)
    invoices = [
        invoice_get(ctx, invoice_get.input(id=row.id)).model_dump(mode="json")
        for row in _every_row(ctx, INVOICE_LIST)
    ]
    return {
        "format": "erplora.account-export",
        "version": 1,
        "exported_at": timezone.now(),
        "account": _export_account(user),
        "preferences": preferences_of(user),
        "photo": photo.data_url() if photo is not None else None,
        "email_addresses": list(
            EmailAddress.objects.filter(user=user).order_by("-primary", "email").values("email", "verified", "primary")
        ),
        "connected_accounts": list(
            SocialAccount.objects.filter(user=user)
            .order_by("provider", "uid")
            .values("provider", "uid", "date_joined", "last_login")
        ),
        "sessions": _export_sessions(user),
        "api_keys": [
            {
                "name": key.name,
                "prefix": key.display_prefix,
                "scopes": list(key.scopes or []),
                "created_at": key.created_at,
                "expires_at": key.expires_at,
                "last_used_at": key.last_used_at,
                "revoked_at": key.revoked_at,
            }
            for key in ApiKey.objects.filter(user=user).order_by("-created_at", "-pk")
        ],
        "businesses": [row.model_dump(mode="json") for row in _every_row(ctx, BUSINESS_LIST)],
        "invoices": invoices,
    }
