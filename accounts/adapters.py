"""allauth adapters of saas-next.

Sign-up is open, as in today's SaaS (ADR-0154): an email without an account creates one on the «Create
account» tab of the launcher (allauth's own sign-up; the sign-in tab never creates one), and a Google email
without one creates it on the way back from Google. Every sign-in with a password also asks for the code mailed to the account
(``ACCOUNT_LOGIN_BY_CODE_REQUIRED``, ``AccountAdapter.is_login_by_code_required``), except the store review account's
(ACCOUNTS-F49). Every way back from
Google that does not sign in lands on a Vue page: «Cancel» on the sign-in (``/launch``), any refusal or
failure on ``/login/error?code=…``, both keeping ``next``.
Google links to an account only by signing in with a Google that proves the account's own address;
``SocialAccountAdapter`` is ported from ERPlora/saas ``ERPloraSocialAccountAdapter``
(``apps/auth/users/adapters.py``, saas#2552).
"""

import logging
import unicodedata
from types import SimpleNamespace
from urllib.parse import urlencode

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.account.utils import has_verified_email
from allauth.core import context as allauth_context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.core.internal.httpkit import HTTP_USER_AGENT_MAX_LENGTH
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthProcess
from allauth.socialaccount.providers.base.constants import AuthError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.shortcuts import redirect
from django.utils import timezone, translation
from django.utils.translation import gettext

from accounts.handoff import login_error_url
from base import emails as branded_mail

logger = logging.getLogger(__name__)

#: The Vue sign-in: the launcher's (``hubs/frontend/pages/LaunchPage.vue``, ``SignInForm.vue``).
SPA_LOGIN = "/launch"


def _login_url(next_url: str | None) -> str:
    """The Vue sign-in, keeping where the person was going (``/hub-login/?hub=…``); the launcher itself
    needs no ``next`` to come back to itself."""
    if not next_url or next_url == SPA_LOGIN:
        return SPA_LOGIN
    return f"{SPA_LOGIN}?{urlencode({'next': next_url}, safe='/')}"


def _with_next(next_url: str | None) -> dict[str, str]:
    return {"next": next_url} if next_url else {}


def folded_email(email: str) -> str:
    """An address with the compatibility forms of its letters folded (NFKC), trimmed and in lower case: the form
    an account keeps, so «Ana@EXAMPLE.com» and «ana@ｅxample.com» are Ana's address (also when inviting it,
    ``hubs.schemas``; ERPlora/saas#2562)."""
    return unicodedata.normalize("NFKC", email).strip().lower()


def plain_email(email: str) -> str:
    """An address in its plain form (``folded_email``), as today's SaaS (ERPlora/saas#1018). «ana@ｅxample.com»
    is Ana's address, never a second account that looks the same, and a look-alike spends the account's budget
    of failed sign-ins, never one of its own. What the folding turns into an invalid address is refused as one."""
    email = folded_email(email)
    validate_email(email)
    return email


def _is_store_review_account(user) -> bool:
    return user is not None and user.is_store_review_account and not (user.is_staff or user.is_superuser)


class AccountAdapter(DefaultAccountAdapter):
    def is_login_by_code_required(self, login) -> bool:
        """The mailed sign-in code (``ACCOUNT_LOGIN_BY_CODE_REQUIRED``), unless the login already waits for
        the code that proves its address: one code, never two.

        allauth asks for the sign-in code before it checks the address (its stages: login by code, then
        email verification), so a sign-up or an address never proven would get the sign-in code, which
        proves the address too. They get the verification code instead, the mail that says what it is for
        («… to register an account on erplora.com»): ``EmailVerificationStage`` mails it and the login
        waits for it (``ACCOUNT_EMAIL_VERIFICATION = "mandatory"``), the same proof of the mailbox.

        The store review account (ACCOUNTS-F49) signs in with its password alone, its address proven: the reviewer of
        Google Play or the App Store has no access to its mailbox. Never an account of the staff, whose sign-in
        leads to the admin (the model refuses the mark on one; a row written past it still gets the code). The
        authenticator app, if it has one, still asks for its code.
        """
        if login.signup or (login.user is not None and not has_verified_email(login.user, login.email)):
            return False
        if _is_store_review_account(login.user):
            return False
        return super().is_login_by_code_required(login)

    def clean_email(self, email: str) -> str:
        """The sign-up's and the password reset's address in its plain form (``plain_email``); the sign-in's is
        folded by its own door (``doors.login``)."""
        return super().clean_email(plain_email(email))

    def clean_password(self, password, user=None):
        """A new password is never the account's current one (ERPlora/saas#2612): «Change password» and the key
        of «Forgot your password?» both ask for a new one. A new account has no password to compare."""
        if user is not None and user.check_password(password):
            raise ValidationError(gettext("Your new password must be different from the current one."), code="password_unchanged")
        return super().clean_password(password, user=user)

    def format_email_subject(self, subject):
        """No ``[site.name]`` prefix: allauth takes it from the ``Site`` row (``example.com``)."""
        return subject

    def send_mail(self, template_prefix, email, context):
        """allauth's mails name ERPlora's public host (``PUBLIC_HOST``), never the ``Site`` row's.

        allauth puts the ``Site`` row in every mail as ``current_site`` («… to register an account on
        example.com»). The brand is written, not looked up (``templates/account/email/base_message.txt``):
        a misconfigured row must not make the first mail of an account read like phishing. As ERPlora/saas
        ``apps/core/emails.py`` (``brand_context``).
        """
        brand = SimpleNamespace(name="ERPlora", domain=settings.PUBLIC_HOST)
        return super().send_mail(template_prefix, email, {**context, "current_site": brand, **branded_mail.brand()})

    def render_mail(self, template_prefix, email, context, headers=None):
        """Every allauth mail leaves as text and as HTML on the common template (ACCOUNTS-F46).

        A notice ERPlora wrote has its own ``<prefix>_message.html`` (``templates/socialaccount/email/``); the
        mails allauth ships come only as text, so their text is shown on the common template, escaped, with the
        code boxed (``base.emails``): one wrapper for all, as ERPlora/saas ``emails/_fallback.html``, instead of
        a copy of each of allauth's texts and translations.
        """
        message = super().render_mail(template_prefix, email, context, headers=headers)
        if isinstance(message, EmailMultiAlternatives) and not any(
            mimetype == "text/html" for _content, mimetype in message.alternatives
        ):
            message.attach_alternative(
                branded_mail.branded_html(
                    message.body.splitlines(),
                    language=translation.get_language() or settings.LANGUAGE_CODE,
                    subject=message.subject,
                    code=context.get("code"),
                ),
                "text/html",
            )
        return message


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google links to an account only by signing in with it, and the owner is told."""

    #: The one allauth notice ERPlora sends: a new way into the account.
    LINKED_NOTICE = "socialaccount/email/account_connected"

    def pre_social_login(self, request, sociallogin):
        """Refuse allauth's «connect» process: it attached ANY Google to the open session's account.

        ERPlora has no screen that connects a provider. The way Google gets linked is signing in
        with a Google that vouches for the account's own address (SAAS_AUTH-F04). allauth's
        re-authentication is no guard here: it waves through an account that has no password.
        A connect posted anyway lands on the Vue error page, which says how Google gets linked
        (``google_link_refused``), keeping ``next``.
        """
        if sociallogin.state.get("process") == AuthProcess.CONNECT:
            logger.warning("google.connect_refused user=%s", request.user.pk)
            next_url = sociallogin.state.get("next")
            raise ImmediateHttpResponse(redirect(login_error_url("google_link_refused", **_with_next(next_url))))
        super().pre_social_login(request, sociallogin)

    def is_open_for_signup(self, request, sociallogin) -> bool:
        """A Google email creates an account only when Google vouches for it (``email_verified``).

        Otherwise whoever holds that Google would get a session for an address they never proved, and keep
        the Google link once the mailbox's owner claims the account with «Forgot your password?». Refused
        as any other failure of the round trip: the Vue error page, keeping ``next``.
        """
        addresses = sociallogin.email_addresses
        if addresses and all(address.verified for address in addresses):
            return super().is_open_for_signup(request, sociallogin)
        logger.warning("google.unverified_email_signup_refused")
        next_url = sociallogin.state.get("next")
        raise ImmediateHttpResponse(redirect(login_error_url("authentication_error", **_with_next(next_url))))

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        """«Cancel» on Google's screen goes back to the sign-in; any other failure is logged and goes
        to the error page. Both keep ``next``: allauth's own answer (``?error=`` on the page it came from) is never
        reached."""
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
