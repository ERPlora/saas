"""An invitation never hands a business to an account that never proved its email (saas#2541; L1-A2).

Ported from ERPlora/saas ``apps/dashboard/hubs/main/tests/test_invite_unverified_account.py``
(origin/develop) to ``hubs.member.invite`` and ``hubs.invitation.accept``. Anybody who can sign up with
somebody else's address and never confirm it would otherwise be the one invited: the membership is the
access (ADR-0201) and the invitation finds the account by its email. The rule: **an email nobody proved
reserves nothing** (``accounts.queries.email_is_proven``). Inviting it releases the account
(``accounts.services.release_unproven_account``): its password, second factor and linked Google go, its
sessions in the SaaS end with the password and in every hub by a ``SessionRevocation``, and the mail
says how to claim the account, so only whoever opens the mailbox gets in. Accepting needs the address
proved (403 ``hubs.email_unverified``).

Accounts that did prove their email, and accounts with nothing to prove (no address on record: made by
an invitation, by the console or by staff), are left alone. Dropped with their reason: the API's JWT and
refresh tokens (the SaaS signs in by session only) and the Hub's device door ``provision_hub_member``
(no runtime pushes members up any more).
"""

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from live.errors import Conflict, PermissionDenied

from hubs import services
from hubs.models import HubMember, SessionRevocation
from hubs.schemas import ByIdIn, MemberInviteIn
from hubs.tests.conftest import ctx_for, member_of

pytestmark = pytest.mark.django_db

User = get_user_model()

PASSWORD = "Squatt3r-pass-phrase"
VICTIM = "ana@example.com"


def invite(owner, hub, email=VICTIM, role="hub_employee"):
    return services.member_invite(
        ctx_for(owner), MemberInviteIn(hub_id=hub.id, email=email, role=role)
    )


def accept(user, hub):
    return services.invitation_accept(ctx_for(user), ByIdIn(id=member_of(hub, user).id))


@pytest.fixture
def squatter(db):
    """The whole move: an account with somebody else's address and a password, never confirmed."""
    account = User.objects.create_user(email=VICTIM, password=PASSWORD)
    EmailAddress.objects.create(
        user=account, email=VICTIM, primary=True, verified=False
    )
    return account


def fresh(user):
    return User.objects.get(pk=user.pk)


class TestTheInvitationReleasesAnAccountThatNeverProvedItsEmail:
    def test_the_squatters_password_no_longer_opens_the_account(
        self, business, owner, squatter
    ):
        invite(owner, business)

        assert not fresh(squatter).check_password(PASSWORD)
        assert not fresh(squatter).has_usable_password()

    def test_the_squatters_session_in_the_saas_ends(
        self, client, business, owner, squatter
    ):
        client.force_login(squatter)

        invite(owner, business)

        assert client.get("/api/me").json()["user"] is None

    def test_the_squatters_sessions_in_every_hub_end(self, business, owner, squatter):
        invite(owner, business)

        assert list(SessionRevocation.objects.values_list("user_id", "hub_id")) == [
            (squatter.pk, None)
        ]

    def test_the_squatters_second_factor_and_linked_google_are_removed(
        self, business, owner, squatter
    ):
        from allauth.mfa.models import Authenticator
        from allauth.socialaccount.models import SocialAccount

        Authenticator.objects.create(
            user=squatter, type=Authenticator.Type.TOTP, data={"secret": "x"}
        )
        SocialAccount.objects.create(
            user=squatter, provider="google", uid="squatter-google-uid"
        )

        invite(owner, business)

        assert not Authenticator.objects.filter(user=squatter).exists()
        assert not SocialAccount.objects.filter(user=squatter).exists()

    def test_a_verified_address_that_is_not_the_invited_one_proves_nothing(
        self, business, owner
    ):
        account = User.objects.create_user(email=VICTIM, password=PASSWORD)
        EmailAddress.objects.create(
            user=account, email="squatter@example.com", primary=True, verified=True
        )
        EmailAddress.objects.create(
            user=account, email=VICTIM, primary=False, verified=False
        )

        invite(owner, business)

        assert not fresh(account).has_usable_password()

    def test_the_invitation_still_waits_for_the_owner_of_the_mailbox(
        self, business, owner, squatter
    ):
        row = invite(owner, business)

        member = HubMember.objects.get(pk=row.id)
        assert (member.user_id, member.role, member.accepted_at) == (
            squatter.pk,
            "hub_employee",
            None,
        )

    def test_the_mail_is_the_one_for_somebody_without_an_account_yet(
        self, business, owner, squatter, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            invite(owner, business)

        (message,) = mail.outbox
        assert message.to == [VICTIM]
        assert (
            "/password/reset" in message.body
        )  # how to claim the account: only the mailbox opens it

    def test_whoever_opens_the_mailbox_claims_the_account_and_then_the_business(
        self, client, business, owner, squatter
    ):
        """The way in that is left is the one only the mailbox opens: «Forgot your password?» (allauth);
        then the address is confirmed (allauth's verification, also by mail) and the invitation accepted."""
        invite(owner, business)
        mail.outbox.clear()

        client.post("/accounts/password/reset/", {"email": VICTIM})
        assert [m.to for m in mail.outbox] == [[VICTIM]]
        reset_link = next(
            word
            for word in mail.outbox[0].body.split()
            if "/accounts/password/reset/key/" in word
        )
        form_url = client.get(reset_link).url
        client.post(
            form_url,
            {
                "password1": "Real-0wner-pass-phrase",
                "password2": "Real-0wner-pass-phrase",
            },
        )
        assert fresh(squatter).check_password("Real-0wner-pass-phrase")
        EmailAddress.objects.filter(user=squatter, email=VICTIM).update(verified=True)

        accept(fresh(squatter), business)

        assert member_of(business, squatter).accepted_at is not None


class TestAccountsThatHaveNothingToProveAreLeftAlone:
    def test_an_account_with_its_email_confirmed_keeps_its_password(
        self, business, owner
    ):
        account = User.objects.create_user(email=VICTIM, password=PASSWORD)
        EmailAddress.objects.create(
            user=account, email=VICTIM, primary=True, verified=True
        )

        invite(owner, business)

        assert fresh(account).check_password(PASSWORD)
        assert not SessionRevocation.objects.exists()

    def test_an_account_with_no_address_on_record_keeps_its_password(
        self, business, owner
    ):
        """Console-made accounts and invited people who already claimed theirs."""
        account = User.objects.create_user(email=VICTIM, password=PASSWORD)

        invite(owner, business)

        assert fresh(account).check_password(PASSWORD)

    def test_a_staff_account_is_never_invited_and_keeps_its_password(
        self, business, owner
    ):
        account = User.objects.create_user(
            email=VICTIM, password=PASSWORD, is_staff=True
        )
        EmailAddress.objects.create(
            user=account, email=VICTIM, primary=True, verified=False
        )

        with pytest.raises(Conflict) as refused:
            invite(owner, business)

        assert refused.value.code == "hubs.platform_account"
        assert fresh(account).check_password(PASSWORD)

    def test_a_fresh_invitation_says_new_account_and_one_with_a_password_does_not(
        self, business, owner, django_capture_on_commit_callbacks
    ):
        User.objects.create_user(email="known@example.com", password=PASSWORD)

        with django_capture_on_commit_callbacks(execute=True):
            invite(owner, business, email="fresh@example.com")
            invite(owner, business, email="known@example.com")

        fresh_mail, known_mail = mail.outbox
        assert "/password/reset" in fresh_mail.body
        assert "/password/reset" not in known_mail.body

    def test_an_invited_account_without_an_address_on_record_accepts(
        self, business, owner
    ):
        """Made by the invitation, claimed with «Forgot your password?»: the claim itself proved the mailbox."""
        invite(owner, business, email="fresh@example.com")
        account = User.objects.get(email="fresh@example.com")

        accept(account, business)

        assert member_of(business, account).accepted_at is not None


def _set_password_from_the_mailed_link(client, email, password):
    """«Forgot your password?» (allauth, the link of the invitation's mail): the key goes to the mailbox."""
    mail.outbox.clear()
    client.post("/accounts/password/reset/", {"email": email})
    (reset,) = [message for message in mail.outbox if message.to == [email]]
    link = next(word for word in reset.body.split() if "/accounts/password/reset/key/" in word)
    form_url = client.get(link).url
    client.post(form_url, {"password1": password, "password2": password})


class TestTheMailedLinkProvesTheMailbox:
    """Setting the password from the link mailed to the address proves the mailbox (members.spec.ts: a
    newcomer claims the account the invitation made, signs in and accepts)."""

    def test_a_newcomer_who_sets_a_password_from_the_link_accepts(self, client, business, owner):
        invite(owner, business, email="fresh@example.com")

        _set_password_from_the_mailed_link(client, "fresh@example.com", "Real-0wner-pass-phrase")
        assert client.login(email="fresh@example.com", password="Real-0wner-pass-phrase")
        account = User.objects.get(email="fresh@example.com")

        accept(account, business)

        assert member_of(business, account).accepted_at is not None
        assert EmailAddress.objects.filter(user=account, email="fresh@example.com", verified=True, primary=True).exists()

    def test_a_released_squatter_account_claimed_from_the_link_accepts(self, client, business, owner, squatter):
        invite(owner, business)

        _set_password_from_the_mailed_link(client, VICTIM, "Real-0wner-pass-phrase")

        accept(fresh(squatter), business)
        assert EmailAddress.objects.get(user=squatter, email=VICTIM).verified

    def test_signing_in_alone_proves_nothing(self, client, business, owner, squatter):
        """A password typed at the login is no proof of the mailbox: still 403 until the link or a verification."""
        HubMember.objects.create(hub=business, user=squatter, role="hub_employee")
        assert client.login(email=VICTIM, password=PASSWORD)

        with pytest.raises(PermissionDenied) as refused:
            accept(fresh(squatter), business)

        assert refused.value.code == "hubs.email_unverified"


class TestAnUnconfirmedAccountCannotAcceptAnInvitation:
    def test_accepting_is_refused_until_the_address_is_confirmed_and_stamps_nothing(
        self, business, owner
    ):
        account = User.objects.create_user(email=VICTIM, password=PASSWORD)
        EmailAddress.objects.create(
            user=account, email=VICTIM, primary=True, verified=False
        )
        HubMember.objects.create(hub=business, user=account, role="hub_employee")

        with pytest.raises(PermissionDenied) as refused:
            accept(account, business)

        assert refused.value.code == "hubs.email_unverified"
        assert member_of(business, account).accepted_at is None

    def test_once_confirmed_it_accepts(self, business, owner):
        account = User.objects.create_user(email=VICTIM, password=PASSWORD)
        EmailAddress.objects.create(
            user=account, email=VICTIM, primary=True, verified=False
        )
        HubMember.objects.create(hub=business, user=account, role="hub_employee")
        EmailAddress.objects.filter(user=account).update(verified=True)

        accept(account, business)

        assert member_of(business, account).accepted_at is not None
