"""The plan's seat cap (``Plan.max_users``), applied where a seat is spent (saas#2022; plan 2026-10-13, L1-B).

Ported from ERPlora/saas (origin/develop) ``hubs/main/tests/test_hub_seat_limit.py`` and the service it
exercises (``services/members.py``: ``hub_seat_cap``, ``hub_seats_taken``, ``assert_hub_has_a_free_seat``).

What the old code decided and this keeps:

* the seat is spent when somebody is ADDED, i.e. at the invitation (Shopify, Odoo and Business Central
  refuse it there, never when the person walks in), and an unanswered invitation holds its seat:
  ``hub_seats_taken`` counted every ``HubMember`` row, answered or not («the seat is spoken for the
  moment it is granted»). Here an invitation expires after 7 days, and an expired one frees its seat;
* ``0`` caps nothing (every paid plan), and neither does a business without a subscription;
* moving somebody already inside spends no seat, and each business counts only its own people;
* the refusal carries a stable code a client branches on, and its message reads in Spanish.

New here: the refusal is the 409 ``hubs.seat_limit`` with ``limit`` and ``used`` in its envelope (the
panel offers the plan change with the numbers), the members page and the business page say
``seats: {used, limit}`` (``limit: null`` = unlimited), and accepting is refused when the business has
no seat left for the people already inside (invitations sent during the Starter trial, answered after
it ended on Free).

Dropped with their reason: the Hub's reported count of active users and its heartbeat (the Hub reports
nothing on a beat any more: it gets ``max_users`` in the snapshot and gates its own PIN users), the
hub's machine credential (no runtime pushes members up), the htmx fragment with the plan link (SPA: the
link is the panel's, lot L1-D) and the OpenAPI field of the beat.
"""

import json
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone, translation
from live.errors import Conflict

from hubs import queries, services
from hubs.models import HubMember, Plan, Subscription
from hubs.schemas import ByIdIn, MemberInviteIn, MemberListIn, MemberRoleIn
from hubs.tests.conftest import add_member, create_business, ctx_for

pytestmark = pytest.mark.django_db

User = get_user_model()
HOST = "localhost:8001"


def invite(actor, hub, email, role="hub_employee"):
    return services.member_invite(
        ctx_for(actor), MemberInviteIn(hub_id=hub.id, email=email, role=role)
    )


def no_trial(hub):
    """The Free plan's own rights (3 people), as after the 15 days of Starter."""
    Subscription.objects.filter(hub=hub).update(
        trial_end=timezone.now() - timedelta(seconds=1)
    )


def full(business, owner):
    """Free without its trial: the owner and two live invitations take the three seats."""
    no_trial(business)
    invite(owner, business, "one@example.com")
    invite(owner, business, "two@example.com")


def seats(actor, hub):
    return queries.member_list(ctx_for(actor), MemberListIn(hub_id=hub.id)).model_dump(
        mode="json"
    )["seats"]


class TestTheInvitationSpendsTheSeat:
    def test_the_fourth_person_on_free_is_refused_and_nothing_is_written(
        self, business, owner
    ):
        full(business, owner)

        with pytest.raises(Conflict) as refused:
            invite(owner, business, "three@example.com")

        assert refused.value.code == "hubs.seat_limit"
        assert (refused.value.limit, refused.value.used) == (3, 3)
        assert not User.objects.filter(email="three@example.com").exists()

    def test_an_unanswered_invitation_holds_its_seat(self, business, owner):
        full(business, owner)

        assert (
            HubMember.objects.filter(hub=business, accepted_at__isnull=True).count()
            == 2
        )
        assert seats(owner, business) == {"used": 3, "limit": 3}

    def test_an_invitation_goes_through_while_a_seat_is_free(self, business, owner):
        no_trial(business)
        invite(owner, business, "one@example.com")

        assert invite(owner, business, "two@example.com").status == "pending"

    def test_an_expired_invitation_frees_its_seat(self, business, owner):
        full(business, owner)
        HubMember.objects.filter(user__email="two@example.com").update(
            invitation_expires_at=timezone.now()
        )

        assert invite(owner, business, "three@example.com").status == "pending"
        assert seats(owner, business) == {"used": 3, "limit": 3}

    def test_renewing_an_expired_invitation_needs_a_free_seat(self, business, owner):
        full(business, owner)
        HubMember.objects.filter(user__email="two@example.com").update(
            invitation_expires_at=timezone.now()
        )
        invite(owner, business, "three@example.com")
        two = HubMember.objects.get(user__email="two@example.com")

        with pytest.raises(Conflict) as resend:
            services.member_resend(ctx_for(owner), ByIdIn(id=two.id))
        with pytest.raises(Conflict) as again:
            invite(owner, business, "two@example.com")

        assert (resend.value.code, again.value.code) == (
            "hubs.seat_limit",
            "hubs.seat_limit",
        )

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
    def test_the_trial_plan_caps_nobody(self, business, owner):
        for n in range(5):
            invite(owner, business, f"p{n}@example.com")

        assert seats(owner, business) == {"used": 6, "limit": None}

    def test_a_paid_plan_caps_nobody(self, business, owner):
        """``max_users = 0`` is «unlimited» on every paid plan, the same contract ``max_devices`` has."""
        Subscription.objects.filter(hub=business).update(
            plan=Plan.objects.get(slug="pro"), trial_plan=None, trial_end=None
        )
        for n in range(4):
            invite(owner, business, f"p{n}@example.com")

        assert seats(owner, business) == {"used": 5, "limit": None}

    def test_a_business_without_a_subscription_is_not_capped(self, business, owner):
        Subscription.objects.filter(hub=business).delete()
        for n in range(4):
            invite(owner, business, f"p{n}@example.com")

        assert seats(owner, business) == {"used": 5, "limit": None}

    def test_moving_somebody_already_inside_needs_no_free_seat(self, business, owner):
        full(business, owner)
        two = HubMember.objects.get(user__email="two@example.com")

        assert (
            services.member_change_role(
                ctx_for(owner), MemberRoleIn(id=two.id, role="hub_admin")
            ).role
            == "hub_admin"
        )

    def test_a_full_business_does_not_spend_another_ones_seats(
        self, business, owner, make_user
    ):
        """Both counted on their OWN people: a count that forgot its business refuses the roomy one too."""
        full(business, owner)
        lola = make_user("lola@example.com")
        other = create_business(lola, name="Café Lola")
        no_trial(other)

        assert invite(lola, other, "one@example.com").status == "pending"
        assert seats(lola, other) == {"used": 2, "limit": 3}


class TestAcceptingNeedsASeatForThePeopleInside:
    def test_an_invitation_inside_the_cap_is_accepted(self, business, owner):
        full(business, owner)
        one = HubMember.objects.get(user__email="one@example.com")

        row = services.invitation_accept(ctx_for(one.user), ByIdIn(id=one.id))

        assert row.slug == business.slug
        assert seats(owner, business) == {"used": 3, "limit": 3}

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
    def test_invitations_from_the_trial_are_answered_first_come_first_served(
        self, business, owner
    ):
        """Five invited during the Starter trial (unlimited), answered on Free (3): two get in."""
        for n in range(5):
            invite(owner, business, f"p{n}@example.com")
        no_trial(business)
        invited = list(
            HubMember.objects.filter(hub=business, accepted_at__isnull=True).order_by(
                "invited_at", "id"
            )
        )

        for member in invited[:2]:
            services.invitation_accept(ctx_for(member.user), ByIdIn(id=member.id))
        with pytest.raises(Conflict) as refused:
            services.invitation_accept(
                ctx_for(invited[2].user), ByIdIn(id=invited[2].id)
            )

        assert refused.value.code == "hubs.seat_limit"
        assert (refused.value.limit, refused.value.used) == (3, 6)
        assert HubMember.objects.get(pk=invited[2].pk).accepted_at is None


class TestTheRefusal:
    def test_the_envelope_carries_the_limit_and_the_seats_used(
        self, client, business, owner
    ):
        full(business, owner)
        client.force_login(owner)

        response = client.post(
            "/api/hubs/members/invite",
            json.dumps({"hub_id": str(business.id), "email": "three@example.com"}),
            content_type="application/json",
            HTTP_HOST=HOST,
        )

        assert response.status_code == 409
        error = response.json()["error"]
        assert (error["code"], error["limit"], error["used"]) == (
            "hubs.seat_limit",
            3,
            3,
        )
        assert "3" in error["message"]

    def test_the_members_page_and_the_business_page_say_the_seats(
        self, client, business, owner
    ):
        full(business, owner)
        client.force_login(owner)

        members = client.get(
            "/api/hubs/members", {"hub_id": str(business.id)}, HTTP_HOST=HOST
        ).json()
        detail = client.get(
            "/api/hubs/businesses/detail", {"id": str(business.id)}, HTTP_HOST=HOST
        ).json()

        assert members["seats"] == detail["seats"] == {"used": 3, "limit": 3}

    def test_the_refusal_speaks_the_owners_language(self, business, owner):
        """ADR-0199: English is the source and the owner reads Spanish (saas#1425)."""
        full(business, owner)

        with translation.override("es"), pytest.raises(Conflict) as refused:
            invite(owner, business, "three@example.com")

        message = refused.value.message
        assert "This plan covers" not in message, (
            f"the seat refusal fell back to English: {message!r}"
        )
        assert "3" in message, f"the cap stopped being interpolated: {message!r}"

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
    def test_a_refused_invitee_is_told_who_can_fix_it(self, business, owner):
        for n in range(4):
            invite(owner, business, f"p{n}@example.com")
        no_trial(business)
        invited = list(
            HubMember.objects.filter(hub=business, accepted_at__isnull=True).order_by(
                "invited_at", "id"
            )
        )
        for member in invited[:2]:
            services.invitation_accept(ctx_for(member.user), ByIdIn(id=member.id))

        with translation.override("es"), pytest.raises(Conflict) as refused:
            services.invitation_accept(
                ctx_for(invited[2].user), ByIdIn(id=invited[2].id)
            )

        assert "This business" not in refused.value.message  # read in Spanish
        assert refused.value.code == "hubs.seat_limit"


def test_an_ordinary_refusal_carries_no_seats(business, team):
    """The numbers belong to THIS refusal only: «already a member» says nothing about seats."""
    with pytest.raises(Conflict) as refused:
        invite(team["owner"], business, "employee@example.com")

    assert refused.value.code == "hubs.already_member"
    assert "limit" not in refused.value.envelope()["error"]


def test_a_member_added_by_hand_counts_too(business, owner, make_user):
    """However the row got there (the admin of Django, a data migration), it holds a seat."""
    no_trial(business)
    for n in range(2):
        add_member(business, make_user(f"hand{n}@example.com"), HubMember.Role.EMPLOYEE)

    with pytest.raises(Conflict) as refused:
        invite(owner, business, "three@example.com")

    assert refused.value.code == "hubs.seat_limit"
