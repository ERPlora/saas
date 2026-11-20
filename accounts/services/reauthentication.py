"""A recent sign-in (allauth's reauthentication) before a command that hands over access."""

import time

from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import OperationError

from accounts.models import ApiKey
from accounts.queries import account_lookup, ways_in


class ReauthenticationRequired(OperationError):
    """401 ``reauthentication_required``: the command needs a recent sign-in (``ACCOUNT_REAUTHENTICATION_TIMEOUT``).

    Its envelope lists the ``flows`` that confirm it, in allauth.headless's words: ``reauthenticate`` (the password,
    ``POST /_allauth/browser/v1/auth/reauthenticate``), ``mfa_reauthenticate`` (a code of the second factor) and
    ``provider_redirect`` (signing in again with a linked provider through allauth.headless's provider redirect,
    whose ``providers`` it names). The panel confirms and sends the command again."""

    status = 401
    code = "reauthentication_required"

    def __init__(self, flows: list[str], providers: list[str]) -> None:
        super().__init__(gettext("Confirm it's you: enter your password again."))
        self.flows = flows
        self.providers = providers

    def envelope(self) -> dict:
        envelope = super().envelope()
        envelope["error"].update(flows=list(self.flows), providers=list(self.providers))
        return envelope


def require_recent_authentication(ctx: OperationContext) -> None:
    """Refuse unless the caller's session signed in, or confirmed it, within allauth's window.

    Stricter than allauth's ``did_recently_authenticate``, which lets an account with neither a password nor a
    second factor through with nothing to confirm: here any account needs a recent sign-in of its own, and one that
    signs in only with Google confirms by signing in with Google again (allauth records it). A request carrying an
    API key never counts (403 ``api_key_not_allowed``), nor does a context without a request (a system call).
    """
    from allauth.account import app_settings as account_settings
    from allauth.account.authentication import get_authentication_records
    from allauth.account.internal.flows.reauthentication import get_reauthentication_flows

    user = account_lookup.account_of(ctx)
    request = ctx.request
    if isinstance(getattr(request, "auth", None), ApiKey):
        raise OperationError(
            gettext("API keys cannot be used here: this operation is only for signed-in people."),
            code="api_key_not_allowed",
            status=403,
        )
    if request is not None and getattr(request, "user", None) == user:
        records = get_authentication_records(request)
        if records and time.time() - records[-1]["at"] < account_settings.REAUTHENTICATION_TIMEOUT:
            return
    flows = [flow["id"] for flow in get_reauthentication_flows(user)]
    providers = ways_in.linked_providers(user)
    if providers:
        flows.append("provider_redirect")
    raise ReauthenticationRequired(flows, providers)
