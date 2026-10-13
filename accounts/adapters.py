"""allauth adapters of saas-next.

Accounts are created by staff (Django admin, ``demo_seed``): the unified sign-up of today's SaaS
(ADR-0154) is not here yet, so a Google email without an account meets a closed door that says so.
Every way back from Google that does not sign in lands on a Vue page: «Cancel» on the sign-in
(``/login``), any refusal or failure on ``/login/error?code=…``, both keeping ``next``.
Google links to an account only by signing in with a Google that proves the account's own address;
``SocialAccountAdapter`` is ported from ERPlora/saas ``ERPloraSocialAccountAdapter``
(``apps/auth/users/adapters.py``, saas#2552).
"""

import logging
from urllib.parse import urlencode

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.core import context as allauth_context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.core.internal.httpkit import HTTP_USER_AGENT_MAX_LENGTH
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthProcess
from allauth.socialaccount.providers.base.constants import AuthError
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.handoff import login_error_url

logger = logging.getLogger(__name__)

#: The Vue sign-in page (``accounts/frontend/pages/LoginPage.vue``).
SPA_LOGIN = "/login"


def _login_url(next_url: str | None) -> str:
    """The Vue sign-in page, keeping where the person was going (``/hub-login/?hub=…``)."""
    return f"{SPA_LOGIN}?{urlencode({'next': next_url}, safe='/')}" if next_url else SPA_LOGIN


def _with_next(next_url: str | None) -> dict[str, str]:
    return {"next": next_url} if next_url else {}


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request) -> bool:
        return False

    def format_email_subject(self, subject):
        """No ``[site.name]`` prefix: allauth takes it from the ``Site`` row (``example.com``)."""
        return subject


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google links to an account only by signing in with it, and the owner is told."""

    #: The one allauth notice ERPlora sends: a new way into the account.
    LINKED_NOTICE = "socialaccount/email/account_connected"

    def pre_social_login(self, request, sociallogin):
        """Refuse allauth's «connect» process: it attached ANY Google to the open session's account.

        ERPlora has no screen that connects a provider. The way Google gets linked is signing in
        with a Google that vouches for the account's own address (SAAS_AUTH-F04). allauth's
        re-authentication is no guard here: it waves through an account that has no password.
        """
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            logger.warning("google.connect_refused user=%s", request.user.pk)
            messages.error(request, _("Google can only be linked by signing in with the Google account of your email."))
            raise ImmediateHttpResponse(redirect(settings.LOGIN_REDIRECT_URL))
        super().pre_social_login(request, sociallogin)

    def is_open_for_signup(self, request, sociallogin) -> bool:
        """The sign-up is closed: a Google email with no account goes to the page that says so,
        naming the address (a person with several Google accounts sees which one they picked)."""
        if super().is_open_for_signup(request, sociallogin):
            return True
        logger.info("google.no_account")
        params = {"email": sociallogin.user.email, **_with_next(sociallogin.state.get("next"))}
        raise ImmediateHttpResponse(redirect(login_error_url("google_no_account", **params)))

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        """«Cancel» on Google's screen goes back to the sign-in; any other failure is logged and goes
        to the error page. Both keep ``next``, and neither renders allauth's template pages."""
        state = (extra_context or {}).get("state") or {}
        next_url = state.get("next")
        if error == AuthError.CANCELLED:
            raise ImmediateHttpResponse(redirect(_login_url(next_url)))
        logger.warning("google.authentication_error error=%s exception=%r", error, exception)
        raise ImmediateHttpResponse(redirect(login_error_url("authentication_error", **_with_next(next_url))))

    def send_notification_mail(self, template_prefix, user, context=None, email=None):
        """Tell the owner a sign-in method was linked, even with allauth's notices switched off.

        ``ACCOUNT_EMAIL_NOTIFICATIONS`` would also switch on allauth's notices for flows ERPlora
        runs itself (password, email), so only this one goes out.
        """
        if template_prefix != self.LINKED_NOTICE:
            return super().send_notification_mail(template_prefix, user, context=context, email=email)
        request = allauth_context.request
        account_adapter = get_account_adapter(request)
        notice = {
            "timestamp": timezone.now(),
            "ip": account_adapter.get_client_ip(request),
            "user_agent": account_adapter.get_http_user_agent(request)[:HTTP_USER_AGENT_MAX_LENGTH],
            "support_email": settings.SUPPORT_EMAIL,
            **(context or {}),
        }
        return account_adapter.send_mail(template_prefix, email or user.email, notice)
