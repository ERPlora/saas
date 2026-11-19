"""Every plan includes every app on ``/pricing/``: the apps each plan lets a business turn on at once, no app sold
on its own, no tier of apps, and the host the storage answer names.

* Every plan includes every app: no «premium add-ons», no fee per activated app, no «marketplace» in the competitor
  table.
* The storage answer names the host, AWS in its Ireland region, never Hetzner.
"""

from __future__ import annotations

import json
import re
from html import unescape

import pytest
from django.utils import translation

from hubs.models import Plan
from public import pricing
from public.tests.pricing_pages import (
    COLUMNS,
    card_items,
    column_cells,
    faq_page_of,
    get,
    html_of,
    make_plan,
    plan_rows,
    plan_table,
    table_head,
    upgrade_section,
    visible_markup,
    visible_text,
)

pytestmark = [pytest.mark.django_db]


# --- The apps each plan lets a business turn on at once --------------------------------------------------------------
# The Hub caps the apps a business chooses to turn on by its plan's ``max_apps`` (the ones they require do not count;
# 0 = no limit), «as the plans published on the SaaS say»: the page publishes that same number,
# read from the row, in a column of the table and a line of every card.

APPS_HEADER = {"en": "Apps turned on at once", "es": "Apps activadas a la vez"}
DEVICES_HEADER = {"en": "Devices and users", "es": "Dispositivos y usuarios"}
#: «Ilimitadas», as the table's «Dispositivos ilimitados»: «Sin límite» is the old home's false «No limit» per user
#: (public/tests/test_product.py, UNSHIPPED_CLAIMS).
NO_LIMIT = {"en": "Unlimited", "es": "Ilimitadas"}
#: The plans of the table, in its order (the seed's, hubs/0013).
TABLE_ORDER = ("Free", "Starter", "Standard", "Pro", "Enterprise", "Max")


def apps_cells(table: str, language: str = "en") -> list[str]:
    """The «Apps turned on at once» cell of each plan row, in the table's order."""
    return column_cells(table, APPS_HEADER[language])


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_table_compares_the_apps_each_plan_turns_on_at_once_next_to_devices_and_users(client, seeded, language):
    table = plan_table(html_of(client, language=language))
    head = table_head(table)

    assert head[head.index(DEVICES_HEADER[language]) + 1] == APPS_HEADER[language]
    unlimited = NO_LIMIT[language]
    assert apps_cells(table, language) == ["20", "40", "80", unlimited, unlimited, unlimited]
    # Each cell sits under its column: a row's cells carry the head's titles, in its order.
    for row in plan_rows(table):
        assert re.findall(r'<td data-title="([^"]*)"', row) == head[1:]


def test_the_table_reads_the_apps_from_the_rows_not_a_typed_number(client, seeded):
    Plan.objects.filter(slug="free").update(max_apps=0)
    Plan.objects.filter(slug="starter").update(max_apps=7)
    Plan.objects.filter(slug="pro").update(max_apps=150)

    assert apps_cells(plan_table(html_of(client))) == ["Unlimited", "7", "80", "150", "Unlimited", "Unlimited"]


#: The card line the cap goes after: «All apps included» (Free, Starter) or «Everything in …» (the plans above).
CARD_APPS = {
    "en": {
        "Free": ("All apps included", "Up to 20 apps turned on at once"),
        "Starter": ("All apps included", "Up to 40 apps turned on at once"),
        "Standard": ("Everything in Starter", "Up to 80 apps turned on at once"),
        "Pro": ("Everything in Standard", "All the apps turned on at once"),
        "Enterprise": ("Everything in Pro", "All the apps turned on at once"),
        "Max": ("Everything in Enterprise", "All the apps turned on at once"),
    },
    "es": {
        "Gratis": ("Todas las apps incluidas", "Hasta 20 apps activadas a la vez"),
        "Starter": ("Todas las apps incluidas", "Hasta 40 apps activadas a la vez"),
        "Standard": ("Todo lo del plan Starter", "Hasta 80 apps activadas a la vez"),
        "Pro": ("Todo lo del plan Standard", "Todas las apps activadas a la vez"),
        "Enterprise": ("Todo lo del plan Pro", "Todas las apps activadas a la vez"),
        "Max": ("Todo lo del plan Enterprise", "Todas las apps activadas a la vez"),
    },
}


@pytest.mark.parametrize("language", ["en", "es"])
def test_each_card_says_the_apps_it_turns_on_at_once_right_after_what_it_includes(client, seeded, language):
    html = html_of(client, language=language)

    for name, (anchor, line) in CARD_APPS[language].items():
        items = card_items(html, name)
        assert items[items.index(anchor) + 1] == line, (name, items)
        assert items.count(line) == 1, name


def test_the_cards_follow_the_row_when_its_cap_changes(client, seeded):
    Plan.objects.filter(slug="starter").update(max_apps=7)
    Plan.objects.filter(slug="free").update(max_apps=0)
    Plan.objects.filter(slug="pro").update(max_apps=150)
    html = html_of(client)

    assert "Up to 7 apps turned on at once" in card_items(html, "Starter")
    assert "All the apps turned on at once" in card_items(html, "Free")
    assert "Up to 150 apps turned on at once" in card_items(upgrade_section(html), "Pro")
    assert "Up to 40 apps turned on at once" not in html


@pytest.mark.parametrize(
    ("language", "line"), [("en", "Up to 1 app turned on at once"), ("es", "Hasta 1 app activada a la vez")]
)
def test_a_cap_of_one_app_reads_in_the_singular(no_plans, client, language, line):
    make_plan("starter", name_es="Starter", features_es=["Usuarios ilimitados"], max_apps=1)

    assert line in card_items(html_of(client, language=language), "Starter")


def test_without_an_includes_line_the_cap_ends_the_plans_own_features(no_plans, client):
    """Staff may word the features as they like: without «All apps included» nor «Everything in …», the line goes after
    the plan's own lines, before the messages and the trial."""
    make_plan("starter", trial_days=15, max_apps=10, assistant_messages_per_month=0, whatsapp_messages_per_month=40)

    assert card_items(html_of(client), "Starter") == [
        "Unlimited users",
        "Up to 10 apps turned on at once",
        "WhatsApp: 40 messages a month",
        "15-day free trial",
    ]


def test_the_cap_line_is_worked_out_on_the_page_and_never_written_in_the_rows(seeded):
    """The seed does not carry it, so editing ``max_apps`` in the admin is enough for the page to follow."""
    for plan in Plan.objects.all():
        for feature in [*plan.features_en, *plan.features_es]:
            assert "apps turned on" not in feature and "apps activadas" not in feature, (plan.slug, feature)


#: A downgrade over the new plan's limits takes nothing away: the apps turned on stay on,
#: and the users and the files stay; only adding more waits until the business is under the limit.
SWITCH_CAP = {
    "en": (
        "If you are over the new plan's limits, you keep what you have: apps turned on stay on, and your users and "
        "files stay; you just can't add more until you are under the limit."
    ),
    "es": (
        "Si superas los límites del plan nuevo, conservas lo que tienes: las apps activadas siguen activadas, y tus "
        "usuarios y tus archivos se quedan; solo no podrás añadir más hasta estar por debajo del límite."
    ),
}


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_switch_answer_says_a_downgrade_over_the_limits_takes_nothing_away(client, seeded, language):
    with translation.override(language):
        (switch,) = [item for item in pricing.faq_items() if item["key"] == "switch"]
    html = html_of(client, language=language)
    (marked_up,) = [
        entry
        for entry in faq_page_of(html)["mainEntity"]
        if entry["name"] == str(switch["question"])
    ]

    assert str(switch["answer"]).endswith(SWITCH_CAP[language])
    assert SWITCH_CAP[language] in unescape(" ".join(visible_text(html).split()))
    assert SWITCH_CAP[language] in marked_up["acceptedAnswer"]["text"]


@pytest.mark.parametrize(
    ("slug", "language", "line"),
    [
        ("starter", "en", "Up to 40 apps turned on at once"),
        ("standard", "es", "Hasta 80 apps activadas a la vez"),
    ],
)
def test_the_detail_says_the_apps_the_plan_turns_on_at_once(client, seeded, slug, language, line):
    response = get(client, f"/pricing/{slug}/", language)
    # «What's included»: the plan's own lines, not the other plans under it.
    included = response.content.decode().split('<h2 class="text-2xl font-semibold mb-6">', 1)[1].split("</ion-card>", 1)[0]

    assert line in response.context["plan"]["own_features"]
    assert line in included


# --- No app sold on its own, and the host -----------------------------------------------------


def test_no_app_is_sold_on_its_own_and_there_is_no_marketplace(client, seeded):
    """No app is sold on its own and there is no marketplace; every plan includes every app, so the page sells no
    tier of apps either (the tests below)."""
    lowered = visible_markup(html_of(client)).lower()

    # «add-on» stays where it describes a competitor («paid add-on, read-only»): what goes is ours.
    for gone in (
        "premium add-on",
        "premium ones when you need them",
        "add on top",
        "marketplace",
        "per activated module",
        "per-module pricing",
    ):
        assert gone not in lowered, gone
    (pricing_item,) = [item for item in pricing.faq_items() if item["key"] == "pricing"]
    assert "Every plan includes all the apps" in str(pricing_item["answer"])


# --- Every app in every plan -------------------------------------------------------------------------------------
# Every plan includes every app: the page sells no tier of apps («the free apps» on Free, «the premium apps» on the paid
# plans) and does not compare the plans on «Apps included» (``included_level``). ``included_level`` stays, dormant, in
# the model, the Store and the checkout, for when a ``premium`` app exists, but not on the public web.

HERO_EN = (
    "Every plan includes all the apps. Paid plans add unlimited devices, more capacity and higher AI and WhatsApp "
    "quotas."
)
HERO_ES = (
    "Todos los planes incluyen todas las apps. Los de pago añaden dispositivos ilimitados, más capacidad y más "
    "mensajes de IA y WhatsApp."
)


def test_the_hero_says_every_plan_includes_all_the_apps(client, seeded):
    body = " ".join(visible_text(html_of(client)).split())

    assert HERO_EN in body
    assert "free apps" not in body.lower()


def test_the_hero_reads_in_spanish(client, seeded):
    body = " ".join(visible_text(html_of(client, language="es")).split())

    assert HERO_ES in body
    assert "apps gratuitas" not in body


def test_the_meta_description_sells_no_tier_of_apps(client, seeded):
    for language, words in (("en", "Every plan includes all the apps."), ("es", "Todos los planes incluyen todas las apps.")):
        html = html_of(client, language=language)
        description = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        assert words in description, language
        assert "premium" not in description.lower(), language


@pytest.mark.parametrize("language", ["en", "es"])
def test_premium_is_nowhere_on_the_page(client, seeded, language):
    """Neither the cards (hubs/0021), the hero, the table, the FAQ nor its JSON-LD sell a premium tier."""
    html = html_of(client, language=language)

    assert "Pro" in visible_text(html), "control: the page is the plans page"
    assert "premium" not in visible_text(html).lower()
    assert "premium" not in json.dumps(faq_page_of(html)).lower()


@pytest.mark.parametrize(("language", "word"), [("en", r"\bmodules?\b"), ("es", r"\bmódulos?\b")])
def test_the_page_calls_them_apps_never_modules(client, seeded, language, word):
    """The public web's word is «apps» (its menu, /apps/), so the page says «all the apps», as on the home
    (public/tests/test_product.py)."""
    body = " ".join(visible_text(html_of(client, language=language)).split())

    assert ("all the apps" if language == "en" else "todas las apps") in body
    assert not re.search(word, body, re.IGNORECASE), re.search(word, body, re.IGNORECASE)


def test_the_table_compares_no_tier_of_apps(client, seeded):
    table = plan_table(html_of(client))
    head = table.split("</thead>", 1)[0]

    assert "Support" in head, "control: the table has its columns"
    assert len(re.findall(r"<th\b", head)) == COLUMNS
    assert "Apps included" not in table
    for plan in Plan.objects.public():
        assert f'data-title="Apps included">{plan.included_level_label}<' not in table


def test_included_level_stays_a_dormant_field_of_the_plan(seeded):
    """Not on the public web, but kept in the model and in hubs.plan.list (the Store, the checkout)."""
    plans = pricing.plans_on_sale()

    assert {plan.included_level for plan in Plan.objects.public()} >= {"free", "basic"}
    assert all(plan.included_level_label for plan in plans.plans)


def test_the_faq_sells_no_tier_of_apps_and_a_downgrade_deletes_and_turns_nothing_off(client, seeded):
    items = {item["key"]: str(item["answer"]) for item in pricing.faq_items()}

    assert "Every plan includes all the apps, so turning an app on or off never changes your bill." in items["pricing"]
    assert "moving down deletes nothing and turns nothing off" in items["switch"]
    assert "at the end of the period you have already paid for" in items["switch"]
    for key, answer in items.items():
        assert "premium" not in answer.lower(), key
        assert "free apps" not in answer.lower(), key


def test_the_storage_answer_names_aws_in_ireland_and_never_hetzner(client):
    """The servers are on AWS, Ireland region (eu-west-1), for all of Europe; never the Spain region (eu-south-2,
    Aragón)."""
    (storage,) = [item for item in pricing.faq_items() if item["key"] == "storage"]
    answer = str(storage["answer"])

    assert "Amazon Web Services" in answer
    assert "Ireland region (eu-west-1)" in answer
    assert "Spain" not in answer
    for language in ("en", "es"):
        html = html_of(client, language=language)
        assert "Hetzner" not in html
        assert "Falkenstein" not in html
        assert "eu-south-2" not in html
        assert "Aragón" not in html
    spanish = html_of(client, language="es")
    assert "región de Irlanda (eu-west-1)" in spanish
    assert "región de España" not in spanish
