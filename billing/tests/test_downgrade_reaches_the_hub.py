"""BILLING-F11, HUBS-F32 and HUBS-F34 when the paid period ends: a downgrade arrives (PLAN-SAAS §31).

``test_downgrade_at_period_end.py`` proves the downgrade while it waits. This is its other end, over Stripe's signed
webhook and with the Hub double taking the push each COMMIT queues, as in production:

- the new phase of the schedule is what applies it: the pending change is forgotten, its schedule released, and the
  Hub takes a newer photo with what the new plan gives (``max_apps``, ``max_users``, ``max_devices``,
  ``max_storage_bytes``); until then it hears nothing and the business keeps what it paid for;
- a lost webhook arrives through the night's reading of Stripe, and a Hub that is away is still owed the photo;
- what only the old level reached leaves the photo, and nothing else goes;
- a business over the new limits keeps its people and only stops adding more: the next invitation is refused, and
  once a place is free again it goes through. The apps and the files over the limit live in the Hub, which only gets
  the new caps here: its half is its own tests, in ERPlora/hub.
"""

import pytest
from django.test import Client
from django.utils import timezone
from live.errors import Conflict

from apps.models import Module
from billing import services
from billing.models import PlanChangeSchedule
from billing.schemas import PlanChangeIn
from billing.tests.conftest import ctx_for, pay
from billing.tests.stripe_double import event, item, schedule, signed, subscription
from hubs import queries as hub_queries
from hubs import services as hub_services
from hubs.models import Hub, HubMember, Plan, Subscription, SubscriptionItem
from hubs.schemas import ByIdIn, MemberInviteIn
from hubs.tests.conftest import add_member
from hubs.tests.conftest import ctx_for as hub_ctx_for

pytestmark = pytest.mark.django_db

SCHEDULE = "sub_sched_1"
GIB = 1024**3


@pytest.fixture(autouse=True)
def _doubles(stripe_double, hub_double, issuer_identity):
    stripe_double.answer("subscription_schedules.create", schedule())
    stripe_double.answer("subscription_schedules.update", schedule())
    stripe_double.answer("subscription_schedules.release", schedule(status="released"))


@pytest.fixture
def committed(django_capture_on_commit_callbacks):
    """Run ``call`` and then the pushes its COMMIT queued, as a request does."""

    def run(call):
        with django_capture_on_commit_callbacks(execute=True):
            return call()

    return run


@pytest.fixture
def waiting(shop, owner, stripe_double, committed):
    """A business on ``plan`` whose downgrade to Starter waits for the end of the period (what Stripe holds then)."""

    def make(plan="standard", modules=()):
        paid = committed(lambda: pay(shop, plan=plan, modules=modules))
        lines = [item("si_plan", f"price_{plan}_month")] + [item(f"si_{slug}", f"price_{slug}_month") for slug in modules]
        stripe_double.answer("subscriptions.retrieve", subscription(items=lines))
        moment = int(timezone.now().timestamp())
        committed(
            lambda: services.plan_change(
                ctx_for(owner), PlanChangeIn(hub_id=paid.id, plan="starter", interval="month", proration_date=moment)
            )
        )
        return paid

    return make


def attached(*lines) -> dict:
    """The subscription with these items, the schedule that holds it still attached."""
    return {**subscription(items=list(lines)), "schedule": SCHEDULE}


STARTER = item("si_plan", "price_starter_month")
STANDARD = item("si_plan", "price_standard_month")


@pytest.fixture
def stripe_says(stripe_double, committed):
    """Stripe's signed event, read back from Stripe as the webhook does, and the pushes its COMMIT queued."""

    def deliver(live, event_type="customer.subscription.updated"):
        stripe_double.answer("subscriptions.retrieve", live)
        body, header = signed(event(event_type, live))
        response = committed(
            lambda: Client().post(
                "/webhooks/stripe/", body, content_type="application/json", HTTP_STRIPE_SIGNATURE=header,
                HTTP_HOST="localhost:8001",
            )
        )
        assert response.status_code == 200, response.content

    return deliver


def photos(double, hub) -> list[dict]:
    return [call.body for call in double.calls_to("PUT", f"/internal/hubs/{hub.id}/state")]


def photo(double, hub) -> dict:
    """The newest photo of ``hub`` the Hub took (a newer version than the one it had)."""
    sent = photos(double, hub)
    assert sent, f"no photo of {hub.slug} reached the Hub"
    assert sent[-1]["version"] == double.versions[str(hub.id)], "the Hub kept an older photo"
    return sent[-1]


def people_of(hub) -> set:
    return set(HubMember.objects.filter(hub=hub).values_list("user_id", flat=True))


def invite(owner, hub, email="one.more@example.com"):
    return hub_services.member_invite(hub_ctx_for(owner), MemberInviteIn(hub_id=hub.id, email=email))


class TestTheArrival:
    def test_until_the_new_phase_the_business_keeps_its_plan_and_the_hub_hears_nothing(
        self, waiting, hub_double, stripe_says
    ):
        paid = waiting()
        before = photo(hub_double, paid)

        # A renewal of the same plan, with the downgrade still waiting.
        stripe_says(attached(STANDARD))

        assert Subscription.objects.get(hub=paid).plan.slug == "standard"
        assert PlanChangeSchedule.objects.get(hub=paid).plan_slug == "starter"
        assert photo(hub_double, paid)["version"] == before["version"]
        assert before["plan"]["slug"] == "standard"

    def test_the_new_phase_forgets_the_change_and_the_hub_takes_the_new_caps(
        self, waiting, hub_double, stripe_double, stripe_says
    ):
        paid = waiting("pro")
        before = photo(hub_double, paid)

        stripe_says(attached(STARTER))

        assert Subscription.objects.get(hub=paid).plan.slug == "starter"
        assert not PlanChangeSchedule.objects.exists()
        assert stripe_double.last("subscription_schedules.release").args == (SCHEDULE,)
        after = photo(hub_double, paid)
        assert after["version"] > before["version"]
        # The numbers of the catalogue (hubs/0013, 0019 and STORAGE_LIMIT_GIB), so that a change of them is said here.
        assert (before["plan"]["max_apps"], before["plan"]["max_storage_bytes"]) == (0, 20 * GIB)
        plan = after["plan"]
        assert (plan["slug"], plan["max_apps"], plan["max_storage_bytes"], plan["max_users"], plan["max_devices"]) == (
            "starter", 40, 5 * GIB, 0, 0,
        )

    def test_the_same_event_again_changes_nothing(self, waiting, hub_double, stripe_says):
        paid = waiting()
        stripe_says(attached(STARTER))
        version = photo(hub_double, paid)["version"]

        stripe_says(subscription(items=[STARTER]))

        assert photo(hub_double, paid)["version"] == version
        assert Subscription.objects.get(hub=paid).plan.slug == "starter"

    def test_a_lost_webhook_arrives_with_the_night_s_reading(self, waiting, hub_double, stripe_double, committed):
        paid = waiting()
        stripe_double.answer("subscriptions.retrieve", attached(STARTER))

        answer = committed(lambda: services.sync_subscription(Subscription.objects.select_related("hub").get(hub=paid)))

        assert answer == "fixed"
        assert not PlanChangeSchedule.objects.exists()
        assert photo(hub_double, paid)["plan"]["slug"] == "starter"

    def test_with_the_hub_away_the_new_plan_stays_owed(self, waiting, stripe_says, settings):
        paid = waiting()
        settings.HUB_INTERNAL_URL = "http://127.0.0.1:9"

        stripe_says(attached(STARTER))

        hub = Hub.objects.get(pk=paid.pk)
        assert hub.pushed_state_version < hub.state_version
        assert Subscription.objects.get(hub=paid).plan.slug == "starter"
        assert hub_queries.hub_snapshot(paid.id)["plan"]["slug"] == "starter"

    def test_what_only_the_old_level_reached_leaves_the_photo_and_nothing_else_goes(
        self, waiting, hub_double, inventory, stripe_says
    ):
        Module.objects.create(slug="e2e_basic", tier=Module.Tier.BASIC)
        Module.objects.create(slug="e2e_pro", tier=Module.Tier.PRO)
        paid = waiting("pro", modules=["inventory"])
        assert {right["id"] for right in photo(hub_double, paid)["modules"]} == {"e2e_basic", "e2e_pro", "inventory"}
        status = Hub.objects.get(pk=paid.pk).status

        stripe_says(attached(STARTER, item("si_inventory", "price_inventory_month")))

        assert {right["id"]: right["source"] for right in photo(hub_double, paid)["modules"]} == {
            "e2e_basic": "plan",
            "inventory": "purchase",
        }
        assert SubscriptionItem.objects.get(subscription__hub=paid, module_slug="inventory").valid_until is None
        assert Hub.objects.get(pk=paid.pk).status == status


class TestOverTheNewLimits:
    @pytest.fixture
    def five_people(self, shop, owner, make_user):
        """The owner and four more, one of them still answering (it holds its place)."""

        def add(hub):
            for name in ("ana", "berta", "carla"):
                add_member(hub, make_user(f"{name}@example.com"), HubMember.Role.EMPLOYEE)
            add_member(hub, make_user("dora@example.com"), HubMember.Role.EMPLOYEE, accepted=False)
            assert len(people_of(hub)) == 5
            return people_of(hub)

        return add

    def test_over_the_new_plan_s_places_nobody_goes_and_only_the_next_invitation_stops(
        self, waiting, owner, hub_double, five_people, stripe_says
    ):
        # No paid plan caps its people today (0): the staff can, and a downgrade then lands over it.
        Plan.objects.filter(slug="starter").update(max_users=4)
        paid = waiting()
        inside = five_people(paid)

        stripe_says(attached(STARTER))

        assert people_of(paid) == inside
        assert photo(hub_double, paid)["plan"]["max_users"] == 4
        with pytest.raises(Conflict) as refused:
            invite(owner, paid)
        assert (refused.value.code, refused.value.limit, refused.value.used) == ("hubs.seat_limit", 4, 5)
        assert people_of(paid) == inside

    def test_once_a_place_is_free_again_the_invitation_goes_through(
        self, waiting, owner, five_people, stripe_says
    ):
        Plan.objects.filter(slug="starter").update(max_users=4)
        paid = waiting()
        inside = five_people(paid)
        stripe_says(attached(STARTER))
        with pytest.raises(Conflict):
            invite(owner, paid)

        for email in ("ana@example.com", "berta@example.com"):
            member = HubMember.objects.get(hub=paid, user__email=email)
            hub_services.member_remove(hub_ctx_for(owner), ByIdIn(hub_id=paid.id, id=member.pk))
        invite(owner, paid)

        assert len(people_of(paid)) == 4
        assert people_of(paid) - inside != set()

    def test_the_end_of_a_cancelled_plan_lands_on_free_with_the_same_rule(
        self, shop, owner, hub_double, five_people, stripe_says, committed
    ):
        paid = committed(lambda: pay(shop, plan="standard", cancel_at_period_end=True))
        inside = five_people(paid)

        stripe_says(subscription(status="canceled"), "customer.subscription.deleted")

        assert people_of(paid) == inside
        plan = photo(hub_double, paid)["plan"]
        assert (plan["slug"], plan["max_apps"], plan["max_storage_bytes"], plan["max_users"], plan["max_devices"]) == (
            "free", 20, GIB, 3, 1,
        )
        with pytest.raises(Conflict) as refused:
            invite(owner, paid)
        assert (refused.value.code, refused.value.limit, refused.value.used) == ("hubs.seat_limit", 3, 5)
