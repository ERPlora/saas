"""What an account's own changes mean to its businesses (``accounts.signals``; PLAN-SAAS §2.1 and §2.2).

accounts never imports hubs (``accounts ← hubs ← billing``): it sends signals and hubs, connected in
``HubsConfig.ready()``, turns them into what the Hub must learn:

- ``sessions_ended`` (Cuenta → Seguridad closes sessions, a new password, the account deleted) queues one
  ``SessionRevocation`` for every business (no hub: the Hub ends the account's sessions everywhere, its
  admin's too), delivered after the COMMIT and retried by ``reconcile_hub_states`` as any other;
- ``account_deleting`` takes the account out of every business as removing a member does: its pending
  ownership offers (made or received) are cancelled (one pending offer per business would block the owner for
  7 days), its memberships and invitations go with their access mirror (``sync_access``), and every business it
  answered gets a newer snapshot, pushed after the COMMIT, with its owner and admins told;
- allauth's ``email_changed``: the snapshot's ``members[]`` carries the address, so every business the
  account answered gets a newer version, pushed after the COMMIT.
"""

from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from allauth.account.signals import email_changed
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from live.models import OutboxEvent

from accounts import services as account_services
from accounts import signals
from accounts.models import HubMembership
from hubs import events
from hubs.models import Hub, HubMember, HubOwnershipTransfer, SessionRevocation
from hubs.tests.conftest import add_member, create_business

pytestmark = pytest.mark.django_db

REVOKE = "/internal/sessions/revoke"


def version(hub):
    return Hub.objects.get(pk=hub.pk).state_version


def ready(hub):
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.ACTIVE, pending_hub_call="")
    return Hub.objects.get(pk=hub.pk)


def ending(user):
    signals.sessions_ended.send(sender=get_user_model(), user_id=user.pk)


def deleting(user):
    signals.account_deleting.send(sender=get_user_model(), user_id=user.pk)


def offer(business, from_user, to_user):
    return HubOwnershipTransfer.objects.create(
        hub=business, from_user=from_user, to_user=to_user, expires_at=timezone.now() + timedelta(days=7)
    )


class TestSessionsEnded:
    def test_it_queues_one_revocation_of_every_business(self, team):
        ending(team["employee"])

        assert list(SessionRevocation.objects.values_list("user_id", "hub_id")) == [(team["employee"].pk, None)]

    def test_it_reaches_the_hub_after_the_commit(self, team, hub_double, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            ending(team["employee"])

        (call,) = hub_double.calls_to("POST", REVOKE)
        assert call.body == {"user_id": str(team["employee"].pk)}
        assert SessionRevocation.objects.get().delivered_at is not None

    def test_with_the_hub_away_it_stays_queued_for_the_reconciliation(
        self, team, offline_hub, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            ending(team["employee"])

        revocation = SessionRevocation.objects.get()
        assert (revocation.delivered_at, revocation.attempts) == (None, 1)

    def test_closing_sessions_in_the_account_ends_them_in_the_businesses(self, team):
        """Cuenta → Seguridad (``accounts.services.end_sessions``), even with no session left in the SaaS."""
        account_services.end_sessions([], user=team["manager"])

        assert list(SessionRevocation.objects.values_list("user_id", "hub_id")) == [(team["manager"].pk, None)]

    def test_a_new_password_ends_them_too(self, team):
        """accounts' receiver of allauth's ``password_changed`` (its own tests send that signal with a request)."""
        account_services.password_changed_ends_sessions(get_user_model(), user=team["admin"])

        assert list(SessionRevocation.objects.values_list("user_id", "hub_id")) == [(team["admin"].pk, None)]


class TestAccountDeleting:
    def test_every_business_it_answered_gets_a_snapshot_without_it(
        self, business, team, make_user, hub_double, django_capture_on_commit_callbacks
    ):
        business = ready(business)
        paco = make_user("paco@example.com")
        other = ready(create_business(paco, name="Bar Paco", slug="bar-paco"))
        add_member(other, team["employee"], HubMember.Role.MANAGER, invited_by=paco)
        before = {business.pk: version(business), other.pk: version(other)}
        employee_id = team["employee"].pk

        with django_capture_on_commit_callbacks(execute=True):
            deleting(team["employee"])
            team["employee"].delete()

        assert {hub.pk: version(hub) for hub in (business, other)} == {
            business.pk: before[business.pk] + 1,
            other.pk: before[other.pk] + 1,
        }
        pushed = {call.hub_id: call.body for call in hub_double.calls_to("PUT", "/state")}
        assert set(pushed) == {str(business.pk), str(other.pk)}
        for snapshot in pushed.values():
            assert str(employee_id) not in {member["user_id"] for member in snapshot["members"]}

    def test_its_memberships_go_with_their_access_mirror(self, business, team):
        """As removing a member does (``sync_access``): the jump checks ``accounts.HubMembership``."""
        deleting(team["employee"])

        assert not HubMember.objects.filter(user=team["employee"]).exists()
        assert not HubMembership.objects.filter(user=team["employee"]).exists()
        assert HubMembership.objects.filter(user=team["manager"], hub_slug=business.slug).exists()

    def test_a_pending_invitation_goes_and_moves_no_snapshot(self, business, team):
        before = version(business)

        deleting(team["invitee"])

        assert version(business) == before
        assert not HubMember.objects.filter(user=team["invitee"]).exists()

    @pytest.mark.parametrize("side", ["received", "made"])
    def test_a_pending_ownership_offer_it_received_or_made_is_cancelled(self, business, team, side):
        """One pending offer per business (``hubs_transfer_one_pending``): left behind, it would block the owner
        for 7 days."""
        transfer = offer(business, team["admin"], team["manager"])

        deleting(team["manager"] if side == "received" else team["admin"])

        transfer.refresh_from_db()
        assert transfer.status == HubOwnershipTransfer.Status.CANCELLED
        assert transfer.resolved_at is not None

    def test_the_owner_can_offer_the_business_again_at_once(self, business, team):
        offer(business, team["owner"], team["admin"])

        deleting(team["admin"])

        assert offer(business, team["owner"], team["manager"]).status == HubOwnershipTransfer.Status.PENDING

    def test_the_owner_and_the_admins_are_told(self, business, team):
        deleting(team["employee"])

        told = set(OutboxEvent.objects.filter(name=events.MEMBER_CHANGED).values_list("scope_key", flat=True))
        assert {str(team["owner"].pk), str(team["admin"].pk)} <= told


class TestDeletingTheAccountFromThePanel:
    """The whole path: Cuenta → «Eliminar cuenta» (``accounts.profile.delete``) reaches the Hub."""

    def test_its_sessions_end_and_its_businesses_drop_it(
        self, business, owner, ana, password, hub_double, django_capture_on_commit_callbacks
    ):
        from accounts.tests.conftest import api_post, sign_in

        business = ready(business)
        add_member(business, ana, HubMember.Role.ADMIN, invited_by=owner)
        offer(business, owner, ana)
        client = sign_in(Client(), ana.email, password)
        ana_id = ana.pk

        with django_capture_on_commit_callbacks(execute=True):
            response = api_post(client, "/api/accounts/profile/delete")

        assert response.status_code == 200, response.content
        assert SessionRevocation.objects.filter(user_id=ana_id, hub=None).exists()
        assert [call.body for call in hub_double.calls_to("POST", REVOKE)] == [{"user_id": str(ana_id)}]
        snapshot = hub_double.calls_to("PUT", "/state")[-1].body
        assert str(ana_id) not in {member["user_id"] for member in snapshot["members"]}
        assert not HubOwnershipTransfer.objects.filter(hub=business, status=HubOwnershipTransfer.Status.PENDING).exists()


class TestEmailChanged:
    def test_every_business_it_answered_gets_the_new_address(
        self, business, team, hub_double, django_capture_on_commit_callbacks
    ):
        business = ready(business)
        employee = team["employee"]
        before = version(business)
        old = EmailAddress.objects.create(user=employee, email=employee.email, verified=True, primary=True)
        employee.email = "elena@new.example"
        employee.save(update_fields=["email"])
        new = EmailAddress.objects.create(user=employee, email=employee.email, verified=True, primary=False)

        with django_capture_on_commit_callbacks(execute=True):
            email_changed.send(
                sender=EmailAddress, request=None, user=employee, from_email_address=old, to_email_address=new
            )

        assert version(business) == before + 1
        snapshot = hub_double.calls_to("PUT", "/state")[-1].body
        emails = {member["user_id"]: member["email"] for member in snapshot["members"]}
        assert emails[str(employee.pk)] == "elena@new.example"

    def test_an_account_without_businesses_moves_nothing(self, business, team):
        before = version(business)

        email_changed.send(
            sender=EmailAddress, request=None, user=team["stranger"], from_email_address=None, to_email_address=None
        )

        assert version(business) == before
