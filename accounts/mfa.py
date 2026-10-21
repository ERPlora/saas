"""Second factor of saas-next (``allauth.mfa``): an authenticator app (TOTP) and recovery codes.

``allauth.mfa`` is always installed (its table always exists); ``settings.ACCOUNTS_MFA_ENABLED``
decides whether it is used, and is read on every call, so turning it on or off is a matter of the
environment alone:

- ``MFAAdapter``: with the flag off no account «has» a second factor, so allauth's login stage never
  asks for a code, not even an account that kept a TOTP row from a time the flag was on.
- ``MFAFlagMiddleware``: with the flag off the 2FA endpoints do not exist: they answer ``404`` with
  allauth's JSON body ``{"status": 404}`` (the Vue pages read it as «2FA is off»). allauth runs headless
  only, so it has no 2FA template page.
- ``mfa_completed``: whether this session passed the second factor, or signs in from a browser the account
  trusts. The jump to a hub asks it (``services.issue_code``), only with the flag on.
"""

import re

from allauth.account.authentication import get_authentication_records
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.mfa.internal.flows.trust import is_trusted_browser
from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseBase

from accounts import queries

#: allauth's headless 2FA endpoints, of any client: managing the authenticators and giving a code.
HEADLESS_2FA = re.compile(r"^/_allauth/[^/]+/v1/(account/authenticators|auth/2fa)(/|$)")


class MFAAdapter(DefaultMFAAdapter):
    def is_mfa_enabled(self, user, types=None) -> bool:
        """``False`` with the flag off, whatever the account has; otherwise allauth's answer."""
        if not settings.ACCOUNTS_MFA_ENABLED:
            return False
        return super().is_mfa_enabled(user, types=types)


def _refusal(request: HttpRequest) -> HttpResponseBase | None:
    """The 404 of a 2FA endpoint while the flag is off, or ``None`` to let the request through."""
    if settings.ACCOUNTS_MFA_ENABLED or not HEADLESS_2FA.match(request.path_info):
        return None
    return JsonResponse({"status": 404}, status=404)


class MFAFlagMiddleware:
    """With ``ACCOUNTS_MFA_ENABLED`` off, answer 404 for every 2FA endpoint (sync and async)."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if self.is_async:
            return self._acall(request)
        refusal = _refusal(request)
        return refusal if refusal is not None else self.get_response(request)

    async def _acall(self, request: HttpRequest) -> HttpResponseBase:
        refusal = _refusal(request)
        return refusal if refusal is not None else await self.get_response(request)


def mfa_completed(request: HttpRequest) -> bool:
    """Whether the session of ``request`` has passed the second factor.

    «MFA completed» means both:

    1. the signed-in account has an authenticator app (``queries.has_totp``), and
    2. this session's authentication records (allauth's ``account_authentication_methods``) hold an
       entry ``method == "mfa"`` for one of that account's authenticators: a code of the app or a
       recovery code, given at the login stage (``/_allauth/browser/v1/auth/2fa/authenticate``) or
       afterwards by reauthenticating (``…/auth/2fa/reauthenticate``).

    The password, the code mailed at sign-in, Google or Django's own login (``force_login``) record no
    ``mfa`` entry. The records live
    in the session: signing out, or signing in as another account, flushes them.

    Or, instead of 2., the browser is one the account trusts (allauth's ``mfa_trusted`` cookie, ACCOUNTS-F05): the
    trust was given right after a good code in it, within 14 days, and is bound to the account's password and
    authenticators. Its sign-in skipped the app's code, so the jump to a business must not ask for it again.
    """
    user = request.user
    if not queries.has_totp(user):
        return False
    ids = {record.get("id") for record in get_authentication_records(request) if record.get("method") == "mfa"}
    return queries.owns_authenticator(user, ids) or is_trusted_browser(request, user)
