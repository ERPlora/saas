"""BILLING-F13 · ASSISTANT-F25 step 5 · What cancelling a plan will do, before it is confirmed (saas#203).

``billing.plan.cancel`` is the one dangerous write of billing (``risk="high"``): from the panel's assistant its card
first shows what the «Cancel the plan» dialog of Billing says — until when it stays on its plan (the business's own
day), the plan it moves to then, the modules that turn off that day, what Free covers against the people it has, and an
unpaid invoice that cancelling does not void. Its ``ai=`` names that read as its ``preview``
(``billing.plan.cancel_preview``, PLAN §30: «a high write, with its full preview»), which ``live.assistant.preview``
runs as the person with the write's own data. The read refuses what the write refuses (not the owner, not the payer,
nothing to cancel): the model hears it before any card, never a card that cannot be done.
"""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from live import assistant as live_assistant
from live.errors import NotFound, OperationError, PermissionDenied
from live.operations import get as get_operation

from assistant.tests.conftest import answering, fake_provider, fernet_key, provider  # noqa: F401 - the gateway's
from apps.models import Module
from apps.tests.factories import make_app
from assistant.tests.doors import frames
from billing import queries
from billing.models import Invoice
from billing.schemas import HubIn, PlanCancelPreviewOut
from billing.tests.conftest import ctx_for, pay
from hubs.models import Hub, HubMember, Plan, Subscription, SubscriptionItem
from hubs.queries import free_plan
from hubs.tests.conftest import add_member

pytestmark = pytest.mark.django_db

CANCEL = "billing.plan.cancel"
PREVIEW = "billing.plan.cancel_preview"
#: What the card shows, in the order the dialog says it.
SHOWN = ["plan", "paid_until", "then", "modules", "free_users", "free_devices", "people", "unpaid_cents"]


@pytest.fixture(autouse=True)
def _stripe(stripe_double, issuer_identity):
    return stripe_double


def preview(user, hub, language="en") -> dict:
    return queries.plan_cancel_preview(ctx_for(user, language), HubIn(hub_id=hub.id)).model_dump()


def refused(code, call):
    with pytest.raises(OperationError) as error:
        call()
    assert error.value.code == code, error.value.envelope()


def ends_at(hub, moment):
    Subscription.objects.filter(hub=hub).update(current_period_end=moment)


def unpaid(hub, net_cents=2999, tax_cents=630, currency="EUR"):
    return Invoice.objects.create(
        hub=hub,
        kind=Invoice.Kind.INVOICE,
        stripe_invoice_id=f"in_{hub.pk.hex[:8]}",
        payment_status=Invoice.PaymentStatus.OPEN,
        net_cents=net_cents,
        tax_cents=tax_cents,
        total_cents=net_cents + tax_cents,
        currency=currency,
        billed_at=timezone.now(),
    )


def settled(hub, net_cents=2999, tax_cents=630):
    """An invoice of ``hub`` already paid, numbered as it is once paid."""
    return Invoice.objects.create(
        hub=hub,
        kind=Invoice.Kind.INVOICE,
        stripe_invoice_id=f"in_{hub.pk.hex[:8]}",
        payment_status=Invoice.PaymentStatus.PAID,
        paid_at=timezone.now(),
        number="ERP-2026-00001",
        issued_on=timezone.localdate(),
        net_cents=net_cents,
        tax_cents=tax_cents,
        total_cents=net_cents + tax_cents,
        billed_at=timezone.now() - dt.timedelta(days=1),
    )


class TestWhatCancellingWillDo:
    def test_it_stays_on_its_plan_until_the_end_of_the_period_and_then_moves_to_free(self, shop, owner):
        paid = pay(shop)

        answer = preview(owner, paid)

        period_end = Subscription.objects.get(hub=paid).current_period_end
        assert answer["hub_id"] == paid.id
        assert answer["plan"] == Plan.objects.get(slug="starter").translated("name", "en")
        assert answer["paid_until"] == timezone.localtime(period_end, ZoneInfo(paid.timezone)).date()
        assert answer["then"] == free_plan().translated("name", "en")

    def test_its_last_day_is_the_businesss_own_day_not_utcs(self, shop, owner):
        paid = pay(shop)
        ends_at(paid, dt.datetime(2026, 12, 1, 23, 30, tzinfo=dt.UTC))  # 00:30 of the 2nd in Madrid

        assert paid.timezone == "Europe/Madrid"
        assert preview(owner, paid)["paid_until"] == dt.date(2026, 12, 2)

    def test_the_plans_are_named_in_the_persons_language(self, shop, owner):
        paid = pay(shop)

        answer = preview(owner, paid, "es")

        assert answer["plan"] == Plan.objects.get(slug="starter").translated("name", "es")
        assert answer["then"] == free_plan().translated("name", "es")
        assert answer["then"] != free_plan().translated("name", "en")

    def test_without_modules_none_turn_off(self, shop, owner):
        assert preview(owner, pay(shop))["modules"] == ""

    def test_the_modules_that_turn_off_that_day_are_named_by_their_apps(self, shop, owner, inventory):
        Module.objects.create(slug="reports", tier=Module.Tier.ENTERPRISE, price_monthly_cents=500, price_annual_cents=5000)
        make_app("inventory", name_es="Inventario")
        make_app("reports", name_es="Informes")
        paid = pay(shop, modules=("inventory", "reports"))

        assert preview(owner, paid, "es")["modules"] == "Informes y Inventario"
        assert preview(owner, paid, "en")["modules"] == "Inventory and Reports"

    def test_a_module_whose_app_the_catalog_no_longer_knows_is_named_by_its_slug(self, shop, owner, inventory):
        """As the Store names it (saas#2589): it still turns off with the plan."""
        assert preview(owner, pay(shop, modules=("inventory",)))["modules"] == "inventory"

    def test_what_free_covers_against_the_people_it_has_now(self, shop, owner, make_user):
        paid = pay(shop)
        add_member(paid, make_user("ana@example.com"), HubMember.Role.EMPLOYEE, invited_by=owner)
        add_member(paid, make_user("pending@example.com"), HubMember.Role.EMPLOYEE, accepted=False, invited_by=owner)
        free = free_plan()

        answer = preview(owner, paid)

        assert (answer["free_users"], answer["free_devices"]) == (free.max_users or None, free.max_devices or None)
        assert answer["people"] == 3  # the owner, a member and a live invitation, as Businesses counts its seats

    def test_a_free_plan_without_a_limit_says_none_not_zero(self, shop, owner):
        """0 on a plan is «no limit» (``Plan.max_users``): the card leaves it off rather than say «0 people»."""
        paid = pay(shop)
        Plan.objects.filter(pk=free_plan().pk).update(max_users=0, max_devices=0)

        answer = preview(owner, paid)

        assert (answer["free_users"], answer["free_devices"]) == (None, None)

    def test_a_module_already_ended_does_not_turn_off_again(self, shop, owner, inventory):
        """A module cancelled on its own (BILLING-F21) ended on its day: it is not among those the plan takes."""
        Module.objects.create(slug="reports", tier=Module.Tier.ENTERPRISE, price_monthly_cents=500, price_annual_cents=5000)
        paid = pay(shop, modules=("inventory", "reports"))
        SubscriptionItem.objects.filter(subscription__hub=paid, module_slug="reports").update(
            valid_until=timezone.now() - dt.timedelta(minutes=1)
        )

        assert preview(owner, paid)["modules"] == "inventory"

    def test_an_unpaid_invoice_is_said_with_what_is_owed(self, shop, owner):
        paid = pay(shop, status="past_due")
        unpaid(paid, net_cents=2999, tax_cents=630)

        answer = preview(owner, paid)

        assert (answer["unpaid_cents"], answer["currency"]) == (3629, "EUR")

    def test_without_an_unpaid_invoice_nothing_is_owed(self, shop, owner):
        answer = preview(owner, pay(shop))

        assert answer["unpaid_cents"] is None

    def test_a_paid_invoice_is_not_owed(self, shop, owner):
        paid = pay(shop)
        settled(paid)

        assert preview(owner, paid)["unpaid_cents"] is None

    def test_a_credit_note_is_not_owed(self, shop, owner):
        """A rectifying invoice is born «not collected» (``Invoice.payment_status``) but gives money back: never a debt."""
        paid = pay(shop)
        Invoice.objects.create(
            hub=paid,
            kind=Invoice.Kind.CREDIT_NOTE,
            rectifies=settled(paid),
            stripe_invoice_id=f"in_{paid.pk.hex[:8]}",
            stripe_source_id="cn_1",
            net_cents=-2999,
            tax_cents=-630,
            total_cents=-3629,
            billed_at=timezone.now(),
        )

        assert preview(owner, paid)["unpaid_cents"] is None

    def test_a_plan_already_cancelled_still_says_until_when(self, shop, owner):
        """Cancelling again changes nothing (BILLING-F13): its preview says the same end."""
        paid = pay(shop, cancel_at_period_end=True)

        assert preview(owner, paid)["paid_until"] is not None

    def test_it_asks_stripe_nothing(self, shop, owner, stripe_double):
        preview(owner, pay(shop))

        assert stripe_double.calls == []


class TestItRefusesWhatTheCancelRefuses:
    def test_a_free_business_has_nothing_to_cancel(self, shop, owner):
        refused("billing.nothing_to_cancel", lambda: preview(owner, shop))

    def test_a_deleted_business_shows_no_card_either(self, shop, owner):
        """As the cancel (``services._owned``): a business deleted, still within its 90 days, takes no write."""
        paid = pay(shop)
        Hub.objects.filter(pk=paid.pk).update(status=Hub.Status.DELETING, deletion_requested_at=timezone.now())

        refused("hubs.business_deleted", lambda: preview(owner, paid))

    @pytest.mark.parametrize("role", [HubMember.Role.ADMIN, HubMember.Role.EMPLOYEE])
    def test_nobody_but_the_owner_reads_it(self, shop, owner, make_user, role):
        paid = pay(shop)
        other = make_user("other@example.com")
        add_member(paid, other, role, invited_by=owner)

        with pytest.raises(PermissionDenied):
            preview(other, paid)

    def test_a_stranger_does_not_learn_the_business_exists(self, shop, make_user):
        paid = pay(shop)

        with pytest.raises(NotFound):
            preview(make_user("stranger@example.com"), paid)

    def test_the_owner_of_another_business_reads_only_its_own(self, shop, owner, make_user, plans):
        from hubs.tests.conftest import create_business

        paid = pay(shop)
        neighbour = make_user("neighbour@example.com")
        theirs = pay(create_business(neighbour, name="Bar Vecino"), sub_id="sub_2", customer="cus_2")

        with pytest.raises(NotFound):
            preview(neighbour, paid)
        assert preview(neighbour, theirs)["hub_id"] == theirs.id

    def test_a_new_owner_does_not_read_the_previous_owners_plan(self, shop, owner, make_user):
        from billing.tests.test_checkout import transferred

        paid = pay(shop)
        new_owner = transferred(paid, owner, make_user)

        refused("billing.payer_required", lambda: preview(new_owner, paid))

    def test_a_plan_still_paid_with_the_previous_owners_card_is_refused_too(self, shop, owner, make_user):
        """The new owner already says who pays, but the plan is still billed to the previous owner's customer: as
        the cancel, it is kept with their card first («Keep it with my card», HUBS-F28)."""
        from billing.tests.test_checkout import transferred
        from hubs import services as hub_services
        from hubs.schemas import BillingProfileIn
        from hubs.tests.conftest import ctx_for as hub_ctx

        paid = pay(shop)
        new_owner = transferred(paid, owner, make_user)
        hub_services.billing_profile_update(
            hub_ctx(new_owner),
            BillingProfileIn(hub_id=paid.id, billing_name="Nuevo SL", billing_country="ES", billing_postal_code="28002"),
        )

        refused("billing.payer_required", lambda: preview(new_owner, paid))

    @pytest.mark.parametrize("status", ["canceled", "incomplete_expired"])
    def test_a_subscription_that_already_ended_has_nothing_to_cancel(self, shop, owner, status):
        paid = pay(shop)
        Subscription.objects.filter(hub=paid).update(status=status)

        refused("billing.nothing_to_cancel", lambda: preview(owner, paid))


class TestTheCardOfTheCancel:
    def test_the_cancel_declares_this_read_as_its_preview(self):
        declared = get_operation(CANCEL).ai_spec()
        read = get_operation(PREVIEW)

        assert declared.risk == "high"
        assert declared.preview == {"operation": PREVIEW, "fields": SHOWN}
        assert (read.kind, read.permission, read.input) == ("query", get_operation(CANCEL).permission, HubIn)
        assert set(SHOWN) <= set(PlanCancelPreviewOut.model_fields)

    def test_the_card_says_it_in_the_persons_language(self, shop, owner, inventory):
        paid = pay(shop, status="past_due", modules=("inventory",))
        unpaid(paid)
        cancel = get_operation(CANCEL)

        failure, spanish = live_assistant.preview(ctx_for(owner, "es"), cancel, {"hub_id": str(paid.id)})
        _, english = live_assistant.preview(ctx_for(owner, "en"), cancel, {"hub_id": str(paid.id)})

        assert failure is None
        assert [line["name"] for line in spanish] == SHOWN
        by_name = {line["name"]: line for line in spanish}
        assert by_name["unpaid_cents"]["kind"] == "money"
        assert by_name["unpaid_cents"]["money"] == {"currency": "EUR", "decimals": 2}
        assert by_name["paid_until"]["value"] != Subscription.objects.get(hub=paid).current_period_end.date().isoformat()
        for es, en in zip(spanish, english, strict=True):
            assert es["label"] != en["label"], es["name"]

    def test_what_is_empty_is_not_on_the_card(self, shop, owner):
        _, shown = live_assistant.preview(ctx_for(owner, "en"), get_operation(CANCEL), {"hub_id": str(pay(shop).id)})

        assert "modules" not in [line["name"] for line in shown]
        assert "unpaid_cents" not in [line["name"] for line in shown]

    def test_with_nothing_to_cancel_the_model_hears_it_and_no_card_is_drawn(self, shop, owner):
        failure, shown = live_assistant.preview(ctx_for(owner, "en"), get_operation(CANCEL), {"hub_id": str(shop.id)})

        assert (failure.outcome, failure.code, shown) == ("error", "billing.nothing_to_cancel", None)


class TestFromThePanelsAssistant:
    """The turn of the panel's assistant (``POST /api/assistant/turn``) stops at the card of the cancel with its
    preview; nothing is cancelled (ASSISTANT-F25, step 5)."""

    def cancel_call(self, hub) -> dict:
        return {"call_id": "c1", "name": "billing__plan__cancel", "arguments": json.dumps({"hub_id": str(hub.id)})}

    def turn(self, client, hub):
        call = self.cancel_call(hub)
        messages = [
            {"role": "user", "content": "cancela el plan de la panadería"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
                ],
            },
        ]
        body = {"messages": messages, "pending": [call]}
        return frames(
            client.post("/api/assistant/turn", json.dumps(body), content_type="application/json", HTTP_HOST="localhost:8001")
        )

    def test_its_card_shows_what_cancelling_will_do(self, client, shop, owner, answering, stripe_double):  # noqa: F811
        paid = pay(shop)
        client.force_login(owner)

        got = self.turn(client, paid)

        assert [frame["type"] if isinstance(frame, dict) else frame for frame in got][:1] == ["confirm"]
        card = got[0]["card"]
        assert (card["operation"], card["risk"]) == (CANCEL, "high")
        assert [line["name"] for line in card["preview"]] == ["plan", "paid_until", "then", "free_users", "free_devices", "people"]
        assert stripe_double.calls == []
        assert Subscription.objects.get(hub=paid).cancel_at_period_end is False

    def test_with_nothing_to_cancel_no_card_is_drawn(self, client, shop, owner, answering, fake_provider):  # noqa: F811
        from assistant.tests.conftest import openai_answer

        fake_provider.reply("POST", "/v1/chat/completions", sse=openai_answer("It is on Free already."))
        client.force_login(owner)

        got = self.turn(client, shop)

        executed = got[0]
        assert (executed["type"], executed["name"], executed["outcome"], executed["code"]) == (
            "executed",
            CANCEL,
            "error",
            "billing.nothing_to_cancel",
        )
        assert "confirm" not in [frame["type"] for frame in got if isinstance(frame, dict)]
