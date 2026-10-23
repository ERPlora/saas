"""Handing a business over: ``hubs.ownership.{transfer,accept,decline,cancel}`` (saas#1670; round 17 §2.7).

Ported from ERPlora/saas (origin/develop) ``hubs/main/tests/test_ownership_transfer.py`` and
``dashboard/users/tests/test_ownership_transfer_views.py``, from services and views to operations:
only the owner offers, only to somebody already on the business, the named recipient answers within 7
days, one offer at a time, the outgoing owner stays as admin, nobody is removed, the payer does not
move and the trail survives the accounts. Dropped with their reason: the machine credential (no
runtime acts for the owner any more) and the confirmation page (SPA, lot L1-D).
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied

from accounts.models import HubMembership
from hubs import queries, services
from hubs.models import BillingProfile, Hub, HubMember, HubOwnershipTransfer
from hubs.schemas import (
    BillingProfileGetIn,
    BillingProfileIn,
    BusinessListIn,
    ByIdIn,
    MemberListIn,
    OwnershipTransferIn,
)
from hubs.tests.conftest import add_member, create_business, ctx_for, member_of

pytestmark = pytest.mark.django_db


def offer(actor, hub, to_user):
    member = HubMember.objects.filter(hub=hub, user=to_user).first()
    member_id = member.id if member else HubMember.objects.first().id
    return services.ownership_transfer(
        ctx_for(actor), OwnershipTransferIn(hub_id=hub.id, member_id=member_id)
    )


def accept(user, transfer_id):
    return services.ownership_accept(ctx_for(user), ByIdIn(id=transfer_id))


def roles(hub):
    return dict(
        HubMember.objects.filter(hub=hub, accepted_at__isnull=False).values_list(
            "user__email", "role"
        )
    )


class TestOnlyTheOwnerOffers:
    def test_the_owner_offers_it_for_seven_days(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])

        row = HubOwnershipTransfer.objects.get()
        assert (transfer.status, transfer.from_email, transfer.to_email) == (
            "pending",
            "owner@example.com",
            "admin@example.com",
        )
        assert row.expires_at - row.created_at == pytest.approx(
            timedelta(days=7), abs=timedelta(seconds=5)
        )

    @pytest.mark.parametrize("who", ["admin", "manager", "employee"])
    def test_nobody_else_offers_it(self, business, team, who):
        with pytest.raises(PermissionDenied):
            offer(
                team[who],
                business,
                team["employee" if who != "employee" else "manager"],
            )

    def test_a_stranger_does_not_learn_the_business_exists(self, business, team):
        with pytest.raises(NotFound):
            offer(team["stranger"], business, team["admin"])

    def test_the_recipient_is_told(
        self, business, team, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            offer(team["owner"], business, team["admin"])

        (message,) = mail.outbox
        assert message.to == ["admin@example.com"]


class TestTheRecipientIsAlreadyOnTheBusiness:
    def test_a_plain_employee_is_a_valid_recipient(self, business, team):
        assert offer(team["owner"], business, team["employee"]).status == "pending"

    def test_somebody_who_has_not_answered_the_invitation_is_not(self, business, team):
        with pytest.raises(Conflict) as refused:
            offer(team["owner"], business, team["invitee"])

        assert refused.value.code == "hubs.transfer_target_not_member"

    def test_a_member_of_another_business_is_not(self, business, team, make_user):
        other = create_business(make_user("lola@example.com"), name="Café Lola")
        add_member(other, team["stranger"], HubMember.Role.EMPLOYEE)

        with pytest.raises(Conflict) as refused:
            services.ownership_transfer(
                ctx_for(team["owner"]),
                OwnershipTransferIn(
                    hub_id=business.id, member_id=member_of(other, team["stranger"]).id
                ),
            )

        assert refused.value.code == "hubs.transfer_target_not_member"

    def test_the_owner_already_owns_it(self, business, team):
        with pytest.raises(Conflict) as refused:
            offer(team["owner"], business, team["owner"])

        assert refused.value.code == "hubs.transfer_to_self"


class TestOneOfferAtATime:
    def test_a_second_offer_while_one_waits_is_refused(self, business, team):
        offer(team["owner"], business, team["admin"])

        with pytest.raises(Conflict) as refused:
            offer(team["owner"], business, team["manager"])

        assert refused.value.code == "hubs.transfer_pending"

    def test_an_expired_offer_does_not_block_a_new_one(self, business, team):
        offer(team["owner"], business, team["admin"])
        HubOwnershipTransfer.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        assert offer(team["owner"], business, team["manager"]).status == "pending"
        assert HubOwnershipTransfer.objects.filter(status="expired").count() == 1


class TestAcceptingSwapsTheTwoRolesAndNothingElse:
    def test_the_recipient_becomes_the_only_owner_and_the_outgoing_one_stays_as_admin(
        self, business, team
    ):
        transfer = offer(team["owner"], business, team["employee"])
        before = Hub.objects.get(pk=business.pk).state_version

        accepted = accept(team["employee"], transfer.id)

        assert accepted.status == "accepted"
        assert roles(business) == {
            "owner@example.com": "hub_admin",
            "admin@example.com": "hub_admin",
            "manager@example.com": "hub_manager",
            "employee@example.com": "hub_owner",
        }
        assert (
            HubMembership.objects.get(
                user=team["employee"], hub_slug=business.slug
            ).role
            == "hub_owner"
        )
        assert Hub.objects.get(pk=business.pk).state_version == before + 1
        assert HubOwnershipTransfer.objects.get().resolved_at is not None

    def test_other_businesses_are_untouched(self, business, team, make_user):
        other = create_business(make_user("lola@example.com"), name="Café Lola")
        add_member(other, team["owner"], HubMember.Role.EMPLOYEE)

        accept(team["admin"], offer(team["owner"], business, team["admin"]).id)

        assert member_of(other, team["owner"]).role == "hub_employee"

    def test_the_payer_does_not_move(self, business, team):
        payer = Hub.objects.get(pk=business.pk).billing_profile_id

        accept(team["admin"], offer(team["owner"], business, team["admin"]).id)

        assert Hub.objects.get(pk=business.pk).billing_profile_id == payer

    def test_the_outgoing_owner_is_told(
        self, business, team, django_capture_on_commit_callbacks
    ):
        transfer = offer(team["owner"], business, team["admin"])

        with django_capture_on_commit_callbacks(execute=True):
            accept(team["admin"], transfer.id)

        assert [message.to for message in mail.outbox] == [["owner@example.com"]]

    def test_a_dead_mailer_never_breaks_the_swap(
        self, business, team, monkeypatch, django_capture_on_commit_callbacks
    ):
        """test_ownership_transfer: the mail leaves after the COMMIT and its failure undoes nothing."""
        from hubs import emails

        def boom(*args, **kwargs):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(emails, "send_ownership_accepted", boom)
        transfer = offer(team["owner"], business, team["admin"])

        with django_capture_on_commit_callbacks(execute=True):
            accept(team["admin"], transfer.id)

        assert roles(business)["admin@example.com"] == "hub_owner"
        assert HubOwnershipTransfer.objects.get().status == "accepted"

    def test_accepting_twice_is_refused(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])
        accept(team["admin"], transfer.id)

        with pytest.raises(Conflict) as refused:
            accept(team["admin"], transfer.id)

        assert refused.value.code == "hubs.transfer_answered"


class TestOnlyTheNamedRecipientAnswers:
    @pytest.mark.parametrize("who", ["manager", "owner", "stranger"])
    def test_nobody_else_accepts(self, business, team, who):
        transfer = offer(team["owner"], business, team["admin"])

        with pytest.raises(NotFound):
            accept(team[who], transfer.id)

        assert roles(business)["owner@example.com"] == "hub_owner"

    def test_an_expired_offer_cannot_be_accepted(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])
        HubOwnershipTransfer.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        with pytest.raises(Conflict) as refused:
            accept(team["admin"], transfer.id)

        assert refused.value.code == "hubs.transfer_expired"
        assert roles(business)["owner@example.com"] == "hub_owner"

    def test_a_recipient_who_left_cannot_accept(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])
        services.member_remove(
            ctx_for(team["owner"]), ByIdIn(id=member_of(business, team["admin"]).id)
        )

        with pytest.raises(Conflict) as refused:
            accept(team["admin"], transfer.id)

        assert refused.value.code == "hubs.transfer_answered"

    def test_removing_the_recipient_withdraws_the_offer(self, business, team):
        """HUBS-F27 «Sale»: the offer pending to the person removed is withdrawn, so the owner may offer the
        business to somebody else at once (and the members page stops saying it is offered)."""
        transfer = offer(team["owner"], business, team["admin"])
        services.member_remove(ctx_for(team["owner"]), ByIdIn(id=member_of(business, team["admin"]).id))

        withdrawn = HubOwnershipTransfer.objects.get(pk=transfer.id)
        assert (withdrawn.status, withdrawn.resolved_at is not None) == ("cancelled", True)
        assert offer(team["owner"], business, team["manager"]).status == "pending"

    def test_an_offer_from_somebody_who_no_longer_owns_it_is_stale(
        self, business, team
    ):
        transfer = offer(team["owner"], business, team["admin"])
        HubMember.objects.filter(hub=business, user=team["owner"]).update(
            role="hub_admin"
        )
        HubMember.objects.filter(hub=business, user=team["manager"]).update(
            role="hub_owner"
        )

        with pytest.raises(Conflict) as refused:
            accept(team["admin"], transfer.id)

        assert refused.value.code == "hubs.transfer_stale"
        assert roles(business)["manager@example.com"] == "hub_owner"


class TestDeclineAndCancelLeaveEverythingWhereItWas:
    def test_the_recipient_declines(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])

        assert (
            services.ownership_decline(
                ctx_for(team["admin"]), ByIdIn(id=transfer.id)
            ).status
            == "declined"
        )
        assert roles(business)["owner@example.com"] == "hub_owner"

    def test_the_owner_cancels(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])

        assert (
            services.ownership_cancel(
                ctx_for(team["owner"]), ByIdIn(id=transfer.id)
            ).status
            == "cancelled"
        )

    def test_the_recipient_cannot_cancel_and_the_owner_cannot_decline(
        self, business, team
    ):
        transfer = offer(team["owner"], business, team["admin"])

        with pytest.raises(NotFound):
            services.ownership_cancel(ctx_for(team["admin"]), ByIdIn(id=transfer.id))
        with pytest.raises(NotFound):
            services.ownership_decline(ctx_for(team["owner"]), ByIdIn(id=transfer.id))

    def test_after_a_decline_a_new_offer_is_possible(self, business, team):
        services.ownership_decline(
            ctx_for(team["admin"]),
            ByIdIn(id=offer(team["owner"], business, team["admin"]).id),
        )

        assert offer(team["owner"], business, team["manager"]).status == "pending"

    def test_cancelling_an_answered_offer_is_refused(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])
        accept(team["admin"], transfer.id)

        with pytest.raises(Conflict) as refused:
            services.ownership_cancel(ctx_for(team["owner"]), ByIdIn(id=transfer.id))

        assert refused.value.code == "hubs.transfer_answered"


class TestWhatTheScreensRead:
    def test_the_recipient_sees_the_offer_with_its_businesses(self, business, team):
        offer(team["owner"], business, team["admin"])

        offers = queries.business_list(
            ctx_for(team["admin"]), BusinessListIn()
        ).model_dump(mode="json")["ownership_offers"]

        assert [(o["hub"]["name"], o["from_email"]) for o in offers] == [
            ("Bar Manolo", "owner@example.com")
        ]

    def test_an_expired_offer_is_hidden(self, business, team):
        offer(team["owner"], business, team["admin"])
        HubOwnershipTransfer.objects.update(expires_at=timezone.now())

        assert (
            queries.business_list(
                ctx_for(team["admin"]), BusinessListIn()
            ).ownership_offers
            == []
        )

    def test_the_row_action_disappears_while_an_offer_waits(self, business, team):
        offer(team["owner"], business, team["admin"])

        rows = queries.member_list(
            ctx_for(team["owner"]), MemberListIn(hub_id=business.id)
        ).rows

        assert not any("transfer" in row.actions for row in rows)

    def test_the_owner_sees_the_offer_waiting_on_the_business(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])

        detail = queries.business_get(ctx_for(team["owner"]), ByIdIn(id=business.id))

        assert (detail.pending_transfer.id, detail.pending_transfer.to_email) == (
            transfer.id,
            "admin@example.com",
        )

    def test_the_trail_survives_the_accounts_it_names(self, business, team):
        transfer = offer(team["owner"], business, team["admin"])
        services.ownership_decline(ctx_for(team["admin"]), ByIdIn(id=transfer.id))
        team["admin"].delete()

        row = HubOwnershipTransfer.objects.get()
        assert (row.to_user, row.to_email, row.status) == (
            None,
            "admin@example.com",
            "declined",
        )


# --- Review of L1-A: the payer and the quota of the new owner -------------------------------------


class TestTheNewOwnersPayer:
    """PLAN-SAAS §3.1: a payer is somebody's (``BillingProfile.owner``). The business keeps being paid
    by its payer after the hand-over, but the new owner neither reads nor edits the old owner's data:
    saving a payer gives the business one of their own."""

    def handed_over(self, business, team):
        services.billing_profile_update(
            ctx_for(team["owner"]), BillingProfileIn(hub_id=business.id, billing_name="Olga SL", tax_id="B12345678")
        )
        accept(team["admin"], offer(team["owner"], business, team["admin"]).id)

    def test_the_new_owner_does_not_read_the_old_owners_payer(self, business, team):
        self.handed_over(business, team)

        payer = queries.billing_profile_get(ctx_for(team["admin"]), BillingProfileGetIn(hub_id=business.id))

        assert (payer.billing_name, payer.tax_id, payer.paid_by_another_account) == ("", "", True)
        assert Hub.objects.get(pk=business.pk).billing_profile.billing_name == "Olga SL"  # still paying

    def test_saving_a_payer_gives_the_business_one_of_the_new_owner(self, business, team):
        self.handed_over(business, team)
        old = Hub.objects.get(pk=business.pk).billing_profile_id

        saved = services.billing_profile_update(ctx_for(team["admin"]), BillingProfileIn(hub_id=business.id, billing_name="Adela SL"))

        hub = Hub.objects.get(pk=business.pk)
        assert (saved.billing_name, saved.paid_by_another_account) == ("Adela SL", False)
        assert hub.billing_profile_id != old and hub.billing_profile.owner == team["admin"]
        assert BillingProfile.objects.get(pk=old).billing_name == "Olga SL"

    def test_a_new_owner_at_the_free_limit_cannot_accept(self, business, team):
        from hubs.models import Plan, Subscription

        # The team is in (``team`` put the business on Starter to fit it); the business goes back to Free.
        Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="free"))
        create_business(team["admin"], name="Adela's own")
        transfer = offer(team["owner"], business, team["admin"])

        with pytest.raises(Conflict) as refused:
            accept(team["admin"], transfer.id)

        assert refused.value.code == "hubs.free_hub_limit"
        assert roles(business)["owner@example.com"] == "hub_owner"
