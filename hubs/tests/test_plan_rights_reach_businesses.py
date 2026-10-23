"""HUBS-F31 (HUBS-G101, HUBS-G96): what a plan includes, changed by the staff in the admin, reaches every business on
that plan without waiting for the night.

The trap of ERPlora/saas SAAS_DASHBOARD-F53 and F54: «un cambio de plan o de topes hecho en el admin de Django cambia
lo que se firma sin empujarlo al hub». Here, saving a change to the rights a plan gives (its limits, its level of
modules, its monthly messages) leaves each business on it owing the Hub a newer snapshot, with the modules of the new
level already written, and the next pass of ``reconcile_hub_states`` (every 15 minutes) delivers it. A change that
only touches texts or prices owes nothing.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.forms.models import model_to_dict

from apps.models import Module
from hubs import services
from hubs.models import Hub, Plan, Subscription, SubscriptionItem
from hubs.tests.conftest import create_business

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    client.force_login(get_user_model().objects.create_superuser(email="root@example.com", password="x"))
    return client


@pytest.fixture
def on_starter(make_user, plans):
    """A business that pays Starter, next to the owner's Free one."""
    business = create_business(make_user("payer@example.com"), name="Peluquería Ana")
    Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="starter"))
    return business


def form_data(plan: Plan, **changes) -> dict:
    """The admin's change form of ``plan`` as the staff send it, with ``changes``."""
    post = {}
    for field, value in {**model_to_dict(plan), **changes}.items():
        if field == "id":
            continue
        if isinstance(value, bool):
            if value:
                post[field] = "on"
        elif isinstance(value, (list, dict)):
            post[field] = json.dumps(value)
        else:
            post[field] = "" if value is None else value
    return post


def edit(staff_client, slug: str, **changes):
    plan = Plan.objects.get(slug=slug)
    return staff_client.post(f"/admin/hubs/plan/{plan.pk}/change/", form_data(plan, **changes))


def versions(*businesses):
    return [Hub.objects.get(pk=business.pk).state_version for business in businesses]


def test_a_new_limit_leaves_every_business_on_the_plan_owing_the_hub(staff_client, business, on_starter):
    before = versions(business, on_starter)

    response = edit(staff_client, "starter", max_users=10)

    assert response.status_code == 302
    assert versions(business, on_starter) == [before[0], before[1] + 1]
    starter = Hub.objects.get(pk=on_starter.pk)
    assert starter.pushed_state_version < starter.state_version


def test_the_next_pass_delivers_it(staff_client, on_starter, hub_double):
    services.reconcile()
    edit(staff_client, "starter", max_devices=2, assistant_messages_per_month=400)

    counts = services.reconcile()

    state = hub_double.calls_to("PUT", f"/internal/hubs/{on_starter.id}/state")[-1].body
    assert (state["plan"]["slug"], state["plan"]["max_devices"], state["plan"]["assistant_messages_per_month"]) == (
        "starter",
        2,
        400,
    )
    assert counts["delivered"] >= 1


def test_the_staff_are_told_how_many_businesses_get_it(staff_client, on_starter):
    response = edit(staff_client, "starter", max_users=10)

    told = [str(message) for message in get_messages(response.wsgi_request)]
    assert "1 business on this plan gets the change within 15 minutes." in told


def test_a_new_level_writes_its_modules_before_the_snapshot(staff_client, on_starter):
    Module.objects.create(slug="kitchen", tier="pro")

    edit(staff_client, "starter", included_level="pro")

    rows = SubscriptionItem.objects.filter(subscription__hub=on_starter, source=SubscriptionItem.Source.PLAN)
    assert "kitchen" in rows.values_list("module_slug", flat=True)


def test_a_change_of_texts_or_order_owes_nothing(staff_client, business, on_starter):
    before = versions(business, on_starter)

    response = edit(staff_client, "starter", name_es="Inicial", display_order=99)

    assert response.status_code == 302
    assert versions(business, on_starter) == before
    assert not [str(message) for message in get_messages(response.wsgi_request) if "15 minutes" in str(message)]


def test_a_deleted_business_is_left_alone(staff_client, on_starter, owner):
    Hub.objects.filter(pk=on_starter.pk).update(status=Hub.Status.DELETING)
    before = versions(on_starter)

    edit(staff_client, "starter", max_users=10)

    assert versions(on_starter) == before


@pytest.mark.usefixtures("signup_trial")  # the dormant sign-up trial of Starter, on (no plan lends one since 2026-10-15)
def test_a_business_trying_the_plan_owes_it_too(staff_client, business):
    """Free with Starter's trial in force: Starter's rights are the ones its snapshot carries."""
    before = versions(business)

    edit(staff_client, "starter", max_users=10)

    assert versions(business) == [before[0] + 1]


# --- HUBS-F34: a paid module added in the admin, or moved to another level -------------------------------------------
# What the plans include is every module their level reaches (``queries.modules_included_in``), written per business by
# ``sync_plan_modules``: a module saved in the admin reached nobody until Stripe next spoke of each business.


@pytest.fixture
def whatsapp(settings):
    from apps.tests.factories import make_app

    settings.STRIPE_SECRET_KEY = ""  # no Stripe here: the admin saves and says the prices were not checked
    return make_app("whatsapp_inbox", premium=True)


def module_form(**changes) -> dict[str, str]:
    return {
        "slug": "whatsapp_inbox",
        "tier": "basic",
        "price_monthly_cents": "999",
        "price_annual_cents": "0",
        "stripe_product_id": "",
        "stripe_price_id_monthly": "",
        "stripe_price_id_annual": "",
        "is_active": "on",
        **changes,
    }


def plan_modules(business) -> list[str]:
    return sorted(
        SubscriptionItem.objects.filter(subscription__hub=business, source=SubscriptionItem.Source.PLAN).values_list(
            "module_slug", flat=True
        )
    )


def test_a_new_module_of_a_plans_level_reaches_its_businesses(staff_client, business, on_starter, whatsapp):
    before = versions(business, on_starter)

    response = staff_client.post("/admin/apps/module/add/", module_form(), follow=True)

    assert response.status_code == 200
    assert (plan_modules(on_starter), plan_modules(business)) == (["whatsapp_inbox"], [])
    assert versions(business, on_starter) == [before[0], before[1] + 1]
    told = [str(message) for message in get_messages(response.wsgi_request)]
    assert "1 business whose plan includes it gets the change within 15 minutes." in told


def test_the_next_pass_takes_the_module_to_the_hub(staff_client, on_starter, whatsapp, hub_double):
    services.reconcile()
    staff_client.post("/admin/apps/module/add/", module_form())

    services.reconcile()

    state = hub_double.calls_to("PUT", f"/internal/hubs/{on_starter.id}/state")[-1].body
    assert {"id": "whatsapp_inbox", "source": "plan", "valid_until": None} in state["modules"]


def test_a_module_moved_up_a_level_leaves_the_plans_below(staff_client, on_starter, whatsapp):
    staff_client.post("/admin/apps/module/add/", module_form())
    module = Module.objects.get(slug="whatsapp_inbox")
    before = versions(on_starter)

    staff_client.post(f"/admin/apps/module/{module.pk}/change/", module_form(tier="pro"))

    assert plan_modules(on_starter) == []
    assert versions(on_starter) == [before[0] + 1]


def test_a_change_of_its_prices_owes_nothing(staff_client, on_starter, whatsapp):
    staff_client.post("/admin/apps/module/add/", module_form())
    module = Module.objects.get(slug="whatsapp_inbox")
    before = versions(on_starter)

    response = staff_client.post(f"/admin/apps/module/{module.pk}/change/", module_form(price_monthly_cents="1299"))

    assert response.status_code == 302
    assert versions(on_starter) == before
