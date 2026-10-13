"""allauth adapters of saas-next: accounts are created by staff, not by signing up, and Google
links to an account only by signing in with it."""

import pytest
from allauth.core import context as allauth_context
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.internal.flows.login import complete_login
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.test import RequestFactory

from accounts.adapters import AccountAdapter, SocialAccountAdapter


def test_signup_is_closed():
    assert AccountAdapter().is_open_for_signup(RequestFactory().get("/accounts/signup/")) is False


@pytest.mark.django_db
def test_posting_a_signup_creates_no_account(client):
    response = client.post("/accounts/signup/", {"email": "new@example.com", "password1": "a-long-pass-phrase"})

    assert "account/signup_closed.html" in [t.name for t in response.templates]
    assert not get_user_model().objects.filter(email="new@example.com").exists()


def test_allauth_mails_carry_no_site_prefix_in_the_subject():
    """allauth prefixed «[example.com]» from the `Site` row; the brand is written, not looked up."""
    assert AccountAdapter().format_email_subject("Reset your password") == "Reset your password"


# Linking a Google account to an existing account (ported from ERPlora/saas
# `apps/auth/users/tests/test_google_connect_needs_the_owner.py`, saas#2552, SAAS_AUTH-F04).
#
# The attack: someone with a minute in front of an open session finished allauth's «connect»
# process with THEIR OWN Google account. allauth asked for nothing but the session, so the
# intruder's Google was attached to the victim's account and from then on «Continue with Google»
# signed the intruder in as the victim. ERPlora offers no screen to connect a provider: Google is
# linked only when the person signs in with a Google whose verified address is the account's own.

OWNER_EMAIL = "owner@example.com"
INTRUDER_EMAIL = "intruder@gmail.com"
INTRUDER_UID = "108000000000000000001"
OWNER_UID = "108000000000000000002"


@pytest.fixture
def owner(db, password):
    return get_user_model().objects.create_user(email=OWNER_EMAIL, password=password)


@pytest.fixture
def google_only_owner(owner):
    owner.set_unusable_password()
    owner.save()
    SocialAccount.objects.create(user=owner, provider="google", uid=OWNER_UID)
    return owner


def _request(user):
    request = RequestFactory().get("/auth/google/callback/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = user
    return request


def _google_login(request, uid, email, process):
    """What allauth holds once Google has answered: the account it vouches for and its address."""
    provider = get_social_adapter().get_provider(request, "google")
    login = provider.sociallogin_from_response(
        request, {"sub": uid, "email": email, "email_verified": True, "given_name": "", "family_name": ""}
    )
    login.state = {"process": process}
    return login


def _finish(user, uid, email, process, request=None):
    request = request or _request(user)
    with allauth_context.request_context(request):
        return complete_login(request, _google_login(request, uid, email, process))


def _account_signed_in_by(uid):
    login = SocialLogin(account=SocialAccount(provider="google", uid=uid))
    login.lookup()
    return login.user if login.is_existing else None


def test_the_social_adapter_is_the_ported_one(settings):
    assert settings.SOCIALACCOUNT_ADAPTER == "accounts.adapters.SocialAccountAdapter"
    assert isinstance(get_social_adapter(), SocialAccountAdapter)


@pytest.mark.django_db
class TestConnectingWithAnOpenSession:
    def test_an_intruders_google_is_not_attached_to_the_account(self, google, owner):
        _finish(owner, INTRUDER_UID, INTRUDER_EMAIL, "connect")

        assert not SocialAccount.objects.filter(user=owner).exists()

    def test_so_the_intruders_google_does_not_sign_in_as_the_owner(self, google, owner):
        _finish(owner, INTRUDER_UID, INTRUDER_EMAIL, "connect")

        assert _account_signed_in_by(INTRUDER_UID) is None

    def test_an_account_without_a_password_is_not_open_either(self, google, google_only_owner):
        """allauth's re-authentication waves through an account with no password: not a guard."""
        _finish(google_only_owner, INTRUDER_UID, INTRUDER_EMAIL, "connect")

        assert list(SocialAccount.objects.filter(user=google_only_owner).values_list("uid", flat=True)) == [OWNER_UID]

    def test_it_sends_the_person_back_to_the_launcher_and_tells_why(self, google, owner):
        request = _request(owner)

        response = _finish(owner, INTRUDER_UID, INTRUDER_EMAIL, "connect", request=request)

        assert response.status_code == 302
        assert response.url == "/launch"
        assert [m.level for m in get_messages(request)] == [messages.ERROR]


@pytest.mark.django_db
class TestSigningInWithGoogleStillWorks:
    def test_the_owners_own_google_signs_in_and_is_linked(self, google, owner):
        """The one way Google gets linked: signing in with a Google that vouches for the address."""
        _finish(AnonymousUser(), OWNER_UID, OWNER_EMAIL, "login")

        assert _account_signed_in_by(OWNER_UID) == owner

    def test_a_linked_google_keeps_signing_in(self, google, google_only_owner):
        _finish(AnonymousUser(), OWNER_UID, OWNER_EMAIL, "login")

        assert _account_signed_in_by(OWNER_UID) == google_only_owner

    def test_a_password_nobody_proved_the_address_of_is_wiped(self, google, owner, password):
        """allauth's own defence, as in today's SaaS: an account created for an address its holder
        never verified may have been made by someone else; once Google proves the address, that
        password stops working («Forgot your password?» or Google from then on)."""
        _finish(AnonymousUser(), OWNER_UID, OWNER_EMAIL, "login")

        owner.refresh_from_db()
        assert not owner.has_usable_password()


@pytest.mark.django_db
class TestTheConnectionsPage:
    """allauth's `/accounts/3rdparty/` connected and disconnected providers with the session alone."""

    def test_it_is_not_served(self, client, google, owner):
        client.force_login(owner)

        response = client.get("/accounts/3rdparty/")

        assert response.status_code == 302
        assert response.url == "/launch"

    def test_it_does_not_disconnect_the_owners_google(self, client, google, owner):
        linked = SocialAccount.objects.create(user=owner, provider="google", uid=OWNER_UID)
        client.force_login(owner)

        client.post("/accounts/3rdparty/", {"account": linked.pk})

        assert SocialAccount.objects.filter(pk=linked.pk).exists()


@pytest.mark.django_db
class TestTheOwnerIsToldWhenGoogleIsLinked:
    """A new way into the account is always told to its address (OWASP ASVS V6.3.7; allauth sends
    it only with ACCOUNT_EMAIL_NOTIFICATIONS, which would also switch on notices for flows ERPlora
    runs itself)."""

    def _notices(self):
        return [m for m in mail.outbox if m.to == [OWNER_EMAIL]]

    def test_signing_in_with_the_accounts_google_links_it_and_tells_the_owner(self, google, owner):
        _finish(AnonymousUser(), OWNER_UID, OWNER_EMAIL, "login")

        (notice,) = self._notices()
        assert notice.subject == "Google sign-in was added to your account"
        assert "From now on you can also sign in to your account with Google." in notice.body
        assert "Hello from ERPlora!" in notice.body

    def test_the_notice_says_where_to_turn_if_it_was_not_them(self, google, owner, settings):
        _finish(AnonymousUser(), OWNER_UID, OWNER_EMAIL, "login")

        (notice,) = self._notices()
        assert settings.SUPPORT_EMAIL in notice.body

    def test_an_already_linked_google_signs_in_without_a_notice(self, google, google_only_owner):
        _finish(AnonymousUser(), OWNER_UID, OWNER_EMAIL, "login")

        assert self._notices() == []

    def test_an_unknown_google_gets_no_account_and_nobody_is_mailed(self, google, owner):
        _finish(AnonymousUser(), INTRUDER_UID, INTRUDER_EMAIL, "login")

        assert not get_user_model().objects.filter(email__iexact=INTRUDER_EMAIL).exists()
        assert mail.outbox == []

    def test_a_refused_connect_tells_nobody_anything_was_linked(self, google, owner):
        _finish(owner, INTRUDER_UID, INTRUDER_EMAIL, "connect")

        assert self._notices() == []
