"""``hubs.plan.list`` and ``GET /api/plans``: the plans on sale, for the public web and the panel.

Public (no account): the pricing page reads it before anyone signs up. Adapted from ERPlora/saas
``public/pricing/views.py`` (origin/develop): only ``Plan.objects.public()`` rows, by
``display_order`` then price; each plan's features end with its real trial (``Plan.trial_label``,
saas#2424) unless an upgrade grants none (#809), and the legacy visual separators («───») are
dropped; the trial the sign-up grants (``signup_trial_days``) and the cheapest plan a visitor can
sign up for (``cheapest_slug``: never an ``upgrade_only`` one).
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import translation
from live.context import OperationContext, Scope
from live.operations import get

from hubs import queries
from hubs.models import Plan
from hubs.schemas import PlanListIn

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
URL = "/api/plans"


@pytest.fixture
def seeded():
    call_command("sync_hub_plans", stdout=StringIO())


def anonymous(language="en"):
    return OperationContext(
        scope=Scope("user", "anonymous"), actor=None, language=language
    )


def plan_list(language="en"):
    return queries.plan_list(anonymous(language), PlanListIn()).model_dump(mode="json")


def test_it_is_an_open_query():
    op = get("hubs.plan.list")

    assert (op.kind, op.permission) == ("query", None)


def test_only_the_public_plans_by_display_order_then_price(seeded):
    """``payment-test`` is internal: only staff may buy it, so a visitor never sees it."""
    slugs = [plan["slug"] for plan in plan_list()["plans"]]

    assert slugs == ["free", "starter", "standard", "pro", "enterprise", "max"]


def test_an_inactive_plan_is_not_on_sale(seeded):
    Plan.objects.filter(slug="max").update(is_active=False)

    assert "max" not in [plan["slug"] for plan in plan_list()["plans"]]


def test_the_shape_of_a_plan(seeded):
    starter = next(plan for plan in plan_list()["plans"] if plan["slug"] == "starter")

    with translation.override("en"):
        trial = Plan.objects.get(slug="starter").trial_label
    assert set(starter) == {
        "slug",
        "name",
        "description",
        "price_monthly",
        "price_annual",
        "features",
        "featured_label",
        "max_users",
        "max_devices",
        "trial_period_days",
        "has_trial",
        "support_level_label",
        "included_level_label",
        "upgrade_only",
        "internal_only",
    }
    assert (starter["name"], starter["price_monthly"], starter["price_annual"]) == (
        "Starter",
        "29.99",
        "299.90",
    )
    assert (
        starter["max_users"],
        starter["max_devices"],
        starter["trial_period_days"],
        starter["has_trial"],
    ) == (
        0,
        0,
        15,
        True,
    )
    assert (starter["upgrade_only"], starter["internal_only"]) == (False, False)
    assert starter["features"][-1] == trial == "15-day free trial"
    assert (starter["included_level_label"], starter["support_level_label"]) == (
        "Basic",
        "Email",
    )


def test_the_copy_is_in_the_callers_language(seeded):
    """The language of the request (or of the live stream), not the thread's."""
    with translation.override("en"):
        spanish = plan_list("es")
    standard = next(plan for plan in spanish["plans"] if plan["slug"] == "standard")

    assert standard["featured_label"] == "Recomendado"
    assert standard["features"][-1] == "15 días de prueba gratis"
    assert standard["description"] == Plan.objects.get(slug="standard").description_es
    with translation.override("es"):
        expected = Plan.objects.get(slug="standard")
        assert (standard["support_level_label"], standard["included_level_label"]) == (
            expected.support_level_label,
            expected.included_level_label,
        )
    english = next(
        plan for plan in plan_list("en")["plans"] if plan["slug"] == "standard"
    )
    assert english["featured_label"] == "Recommended"


def test_an_upgrade_never_promises_a_trial(seeded):
    Plan.objects.filter(slug="pro").update(trial_period_days=15)

    pro = next(plan for plan in plan_list()["plans"] if plan["slug"] == "pro")

    assert pro["has_trial"] is True
    assert not any("trial" in feature for feature in pro["features"])


def test_a_plan_without_a_trial_ends_with_its_own_features(seeded):
    free = next(plan for plan in plan_list()["plans"] if plan["slug"] == "free")

    assert free["features"] == Plan.objects.get(slug="free").features_en
    assert free["has_trial"] is False


def test_the_visual_separators_of_old_rows_are_dropped(seeded):
    Plan.objects.filter(slug="free").update(
        features_en=["1 device", "───", "  ", "3 users"]
    )

    free = next(plan for plan in plan_list()["plans"] if plan["slug"] == "free")

    assert free["features"] == ["1 device", "3 users"]


def test_the_signup_trial_is_the_longest_a_new_plan_grants(seeded):
    assert plan_list()["signup_trial_days"] == 15


def test_without_any_trial_the_signup_trial_is_zero(seeded):
    Plan.objects.update(trial_period_days=0)

    assert plan_list()["signup_trial_days"] == 0


def test_the_cheapest_plan_is_the_free_one(seeded):
    assert plan_list()["cheapest_slug"] == "free"


def test_the_cheapest_plan_is_never_an_upgrade_nor_internal(seeded):
    Plan.objects.filter(slug="free").update(is_active=False)
    Plan.objects.create(
        slug="cheap-upgrade",
        name_en="Cheap upgrade",
        price_monthly=Decimal("1"),
        upgrade_only=True,
    )

    assert plan_list()["cheapest_slug"] == "starter"


def test_without_plans_on_sale_there_is_no_cheapest():
    assert plan_list() == {"signup_trial_days": 0, "cheapest_slug": None, "plans": []}


class TestTheRoute:
    def test_an_anonymous_visitor_reads_it(self, client, seeded):
        response = client.get(URL, HTTP_HOST=HOST)

        assert response.status_code == 200
        assert response.json()["cheapest_slug"] == "free"

    def test_an_account_reads_the_same(self, client, seeded):
        anonymous_body = client.get(URL, HTTP_HOST=HOST).json()
        client.force_login(
            get_user_model().objects.create_user(email="ana@example.com", password="x")
        )

        assert client.get(URL, HTTP_HOST=HOST).json() == anonymous_body

    def test_it_speaks_the_language_of_the_request(self, client, seeded):
        body = client.get(URL, HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="es").json()

        assert (
            next(plan for plan in body["plans"] if plan["slug"] == "standard")[
                "featured_label"
            ]
            == "Recomendado"
        )
