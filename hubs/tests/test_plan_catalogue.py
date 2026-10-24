"""Guard tests of the plan catalogue: the rows the migrations leave, which staff keep in the admin after.

The plans live only in the database (Ioan, 2026-10-15): migration ``hubs/0013`` is the seed of a new database
and puts production's rows right once; there is no command that seeds or overwrites them (``sync_hub_plans`` is
an empty command until the deploy stops calling it). pytest builds its database by running every migration, so these tests read the catalogue a new
database starts with.

Ported from ERPlora/saas ``hubs/subscriptions/tests/test_sync_hub_plans.py`` (origin/develop),
plus the seed halves of ``test_plan_trial_label.py`` and ``test_payment_test_plan.py``.

Root cause of the "Spanish plan copy on an English landing" bug: the seed put Spanish into the
English (default-language) fields, so an English visitor saw Spanish. These tests pin the ``_en``
columns to English and keep the ``_es`` mirror in Spanish. saas-next has no modeltranslation: each
language is its own column (``name_en``, ``name_es``…), as in the taxonomy (PLAN §21.4).

Changed from the original:

- ``test_resource_ladder_matches_the_2026_08_15_sizing_decision`` pinned the vCPU and memory of
  each plan: a plan no longer sizes a container (PLAN-SAAS §1). What is left is the DB
  ladder decided in round 9 (PLAN §14.2): Free, 1 transaction at a time and 5 s; paid, 3 and 15 s.
- the tests of the seed command (idempotent, ``--update``, «N created, M existing») went with it on
  2026-10-15; what the migrations write is pinned by ``hubs/tests/test_migrations.py``.
"""

import re
from decimal import Decimal

import pytest
from django.utils import translation

from hubs.models import Plan

pytestmark = pytest.mark.django_db

# Spanish giveaways that must never appear in an English field.
SPANISH_MARKERS = [
    "Usuarios ilimitados",
    "Sin mantenimiento",
    "prueba gratis",
    "Todos los módulos",
    "Todas las apps",
    "Base de datos",
    "Dominio propio",
    "en la nube",
    "Recomendado",
    "recuperacion",
    "recuperación",
]

#: Every field of a plan. An allowlist, so the container sizing PLAN-SAAS §1 drops (and the paused-hub
#: price that went with it) cannot come back without changing this test.
PLAN_FIELDS = {
    "id", "slug", "name_en", "name_es", "description_en", "description_es", "price_monthly", "price_annual",
    "features_en", "features_es", "featured_label_en", "featured_label_es", "is_active", "upgrade_only",
    "internal_only", "stripe_product_id", "stripe_price_id", "stripe_price_id_annual", "trial_period_days",
    "display_order", "max_hubs_per_org", "max_devices", "max_users", "max_db_connections",
    "statement_timeout_seconds", "included_level", "support_level", "includes_custom_domain",
    "assistant_messages_per_month", "whatsapp_messages_per_month", "max_apps",
    "created_at", "updated_at",
    # The reverse relation of Subscription.plan (the hubs on the plan), not a column of the plan.
    "subscriptions",
}  # fmt: skip

PAYMENT_TEST = "payment-test"
#: The catalogue (Ioan, 2026-10-15): three plans on sale at sign-up, the three upgrade-only tiers above them (kept,
#: not retired) and the internal one.
UPGRADE_ONLY = ("pro", "enterprise", "max")
CATALOGUE = ("free", "starter", "standard", *UPGRADE_ONLY, PAYMENT_TEST)


@pytest.fixture
def catalogue():
    """The plans the migrations leave, by slug."""
    return {p.slug: p for p in Plan.objects.all()}


def test_the_catalogue_is_the_plans_on_sale_the_upgrade_only_tiers_and_the_internal_one(catalogue):
    """Ioan, 2026-10-15: Free, Starter and Standard at sign-up; Pro, Enterprise and Max above them, kept as
    upgrades of a business that pays; ``payment-test`` for staff."""
    assert set(catalogue) == set(CATALOGUE)
    assert sorted(slug for slug, plan in catalogue.items() if plan.upgrade_only) == sorted(UPGRADE_ONLY)


def test_no_plan_carries_a_trial(catalogue):
    """Ioan, 2026-10-15: no trial; the Free plan is the way in. The mechanism stays (``trial_period_days``, the
    checkout's ``trial_end``), dormant: a plan only has a trial if staff give it one in the admin."""
    assert {slug: plan.trial_period_days for slug, plan in catalogue.items()} == dict.fromkeys(CATALOGUE, 0)
    assert Plan.objects.signup_trial_days() == {"trial_days_min": None, "trial_days_max": None}


def test_starter_english_fields_are_english(catalogue):
    starter = catalogue["starter"]
    assert (
        starter.description_en
        == "Your whole business in the cloud: nothing to install, nothing to maintain, always available."
    )
    assert "Unlimited users" in starter.features_en
    assert "Fully managed cloud on Amazon Web Services, in Europe, with automatic scaling" in starter.features_en
    for feature in starter.features_en:
        for marker in SPANISH_MARKERS:
            assert marker not in feature, (
                f"Spanish marker {marker!r} leaked into EN feature {feature!r}"
            )


def test_spanish_mirror_is_preserved(catalogue):
    starter = catalogue["starter"]
    assert (
        starter.description_es
        == "Todo tu negocio en la nube: nada que instalar, nada que mantener, siempre disponible."
    )
    assert "Usuarios ilimitados" in starter.features_es
    assert "Cloud gestionado en Amazon Web Services, en Europa, con autoescalado" in starter.features_es


def test_recommended_badge_is_translated(catalogue):
    standard = catalogue["standard"]
    assert standard.featured_label_en == "Recommended"
    assert standard.featured_label_es == "Recomendado"


def test_support_copy_never_promises_a_clock_we_do_not_run(catalogue):
    """saas#1760: support is sold as CHANNEL + PRIORITY, never as an unmeasured clock."""
    for slug, plan in catalogue.items():
        for text in [plan.description_en, *plan.features_en]:
            assert "24/7" not in text, f"[{slug}] unbacked 24/7 support claim: {text!r}"
            assert not re.search(r"\b\d+\s*h(ours?)?\s+response\b", text, re.I), (
                f"[{slug}] unmeasured response-time promise: {text!r}"
            )
        for text in [plan.description_es, *plan.features_es]:
            assert "24/7" not in text, (
                f"[{slug}] unbacked 24/7 support claim (es): {text!r}"
            )
            assert not re.search(r"respuesta\s+en\s+\d+", text, re.I), (
                f"[{slug}] unmeasured response-time promise (es): {text!r}"
            )


def test_support_ladder_still_differentiates_by_channel_and_priority(catalogue):
    """Removing the fake clock must not flatten the ladder into 'support' everywhere."""
    assert any(f == "Community support" for f in catalogue["free"].features_en)
    assert any("Email support" in f for f in catalogue["starter"].features_en)
    assert any(
        "Priority email support" in f for f in catalogue["standard"].features_en
    )
    assert any(f == "Soporte de la comunidad" for f in catalogue["free"].features_es)
    assert any("Soporte por email" in f for f in catalogue["starter"].features_es)
    assert any("prioritario" in f for f in catalogue["standard"].features_es)


def test_no_english_field_contains_spanish(catalogue):
    """Sweep every plan: the English description and features are Spanish-free."""
    for slug, plan in catalogue.items():
        for text in [plan.description_en, *plan.features_en]:
            for marker in SPANISH_MARKERS:
                assert marker not in text, (
                    f"[{slug}] Spanish marker {marker!r} in EN field: {text!r}"
                )


# saas#1760: infra specs that must never reach commercial copy again.
INFRA_SPEC_PATTERNS = [
    (r"\b\d+\s*(MB|GB|TB)\b", "raw memory/storage size"),
    (r"\bv?CPU\b", "CPU spec"),
    (r"\bRAM\b", "RAM spec"),
    (r"\bcompute resources\b", "compute multiplier"),
    (r"\brecursos de computaci", "compute multiplier (es)"),
    (r"\bdatabase connections\b", "DB connection quota"),
    (r"\bconexiones\b", "DB connection quota (es)"),
    (r"\b\d+x\b", "resource multiplier"),
]


def _copy(plan):
    return [
        plan.description_en,
        plan.description_es,
        *plan.features_en,
        *plan.features_es,
    ]


def test_no_plan_sells_infrastructure_specs(catalogue):
    """saas#1760: commercial copy sells the HUB, never the box it runs on."""
    for slug, plan in catalogue.items():
        for text in _copy(plan):
            for pattern, label in INFRA_SPEC_PATTERNS:
                assert not re.search(pattern, text, re.I), (
                    f"[{slug}] {label} in commercial copy: {text!r}"
                )


def test_no_plan_publishes_an_uptime_sla_percentage(catalogue):
    """saas#1760: the only availability statement is the one in the terms (99.5 %, reasonable efforts)."""
    for slug, plan in catalogue.items():
        for text in _copy(plan):
            assert not re.search(r"\d{2}[.,]\d+\s*%", text), (
                f"[{slug}] uptime SLA claim in plan copy: {text!r}"
            )
            assert "SLA" not in text, f"[{slug}] SLA claim in plan copy: {text!r}"


def test_subscription_unit_is_the_hub(catalogue):
    """saas#1760: one subscription buys ONE hub, with every location and device in it. The copy calls it what the
    panel calls it, a business (audit 2 S-12: «Precio por hub» in the Store was the Hub's word)."""
    for slug in ("starter", "standard"):
        plan = catalogue[slug]
        assert any("per business" in f.lower() for f in plan.features_en), (
            f"[{slug}] paid plan never states the billing unit: {plan.features_en}"
        )
        assert any("por negocio" in f.lower() for f in plan.features_es), (
            f"[{slug}] paid plan never states the billing unit (es): {plan.features_es}"
        )
        assert not any(re.search(r"\bhub\b", f, re.I) for f in [*plan.features_en, *plan.features_es]), (
            f"[{slug}] the plan copy speaks of a hub: {plan.features_es}"
        )
        assert plan.max_devices == 0, f"[{slug}] paid plans must not cap devices"


def test_recovery_window_is_the_same_on_every_plan(catalogue):
    """saas#1760 + infra#136: the backup window is physical and common to the cluster."""
    backup_lines_en = {
        line
        for plan in catalogue.values()
        for line in plan.features_en
        if "backup" in line.lower()
    }
    assert backup_lines_en, "the backup promise disappeared entirely"
    assert len(backup_lines_en) == 1, (
        f"backup copy diverges per plan: {backup_lines_en}"
    )
    (backup_line,) = backup_lines_en
    assert "7-day" not in backup_line, f"stale 7-day retention claim: {backup_line!r}"
    assert "point-in-time" in backup_line.lower(), (
        f"copy must describe what infra#136 proved: {backup_line!r}"
    )


#: The database line of Free and Starter: one sentence with the backups, the same words as the public
#: downloads page (``public/templates/public/downloads.html``). Since 2026-10-15 (Ioan) it tells the customer
#: what they get in plain words — where it lives (AWS, Europe) and that it is replicated — never how it is run.
MANAGED_DATABASE = {
    "en": (
        "Managed database, replicated across several European data centres, with continuous backups and "
        "point-in-time recovery for 14 days"
    ),
    "es": (
        "Base de datos gestionada, replicada en varios centros de datos europeos, con copias de seguridad "
        "continuas y recuperación a cualquier momento de los últimos 14 días"
    ),
}
#: Ioan's rule for the public web: the copy sells what the customer gets, never the technology under it.
TECHNOLOGY_NAMES = ("postgresql", "postgres", "aurora")


def _names_a_technology(text: str) -> bool:
    return any(name in text.lower() for name in TECHNOLOGY_NAMES)


def test_no_plan_names_the_technology_under_it(catalogue):
    for slug, plan in catalogue.items():
        for text in _copy(plan):
            assert not _names_a_technology(text), f"[{slug}] technology name in plan copy: {text!r}"


def test_the_technology_guard_catches_the_lines_that_were_actually_published():
    """Positive control: the database lines the seed carried before the rule."""
    for published in ("Managed PostgreSQL database", "Base de datos PostgreSQL gestionada"):
        assert _names_a_technology(published), published


def test_the_database_and_its_backups_are_one_line(catalogue):
    """«Managed database» and «continuous backups» are one sentence, not two lines saying backups twice."""
    for slug in ("free", "starter"):
        plan = catalogue[slug]
        assert MANAGED_DATABASE["en"] in plan.features_en, slug
        assert MANAGED_DATABASE["es"] in plan.features_es, slug
    for plan in catalogue.values():
        assert sum("backup" in line.lower() for line in plan.features_en) <= 1, plan.slug
        assert sum("copias" in line.lower() for line in plan.features_es) <= 1, plan.slug


def test_the_cards_say_where_the_data_lives_and_that_the_database_is_replicated(catalogue):
    """Ioan, 2026-10-15: a buyer reads «Amazon Web Services, in Europe» once per card (the cloud line) and
    «replicated» on the database line, never an engine name."""
    for slug in ("free", "starter"):
        plan = catalogue[slug]
        assert sum("Amazon Web Services" in f for f in plan.features_en) == 1, plan.features_en
        assert sum("Amazon Web Services" in f for f in plan.features_es) == 1, plan.features_es
        (line,) = [f for f in plan.features_en if "backup" in f.lower()]
        assert "replicated" in line, (slug, line)
        (line_es,) = [f for f in plan.features_es if "copias" in f.lower()]
        assert "replicada" in line_es, (slug, line_es)


def test_the_recovery_window_is_the_one_aurora_keeps(catalogue):
    """The card promises the 14 days Aurora keeps (``backup_retention_period = 14``,
    ``aws-next/stacks/prod/aurora.tf``), no more: the old «up to 30 days» was the old cluster's
    (the public web's session, 2026-10-14)."""
    english = {
        line
        for plan in catalogue.values()
        for line in plan.features_en
        if "backup" in line.lower()
    }
    spanish = {
        line
        for plan in catalogue.values()
        for line in plan.features_es
        if "copias" in line.lower()
    }

    assert english == {MANAGED_DATABASE["en"]}
    assert spanish == {MANAGED_DATABASE["es"]}
    assert not any(
        "30" in line
        for plan in catalogue.values()
        for line in [*plan.features_en, *plan.features_es]
    )


def test_the_plans_promise_the_free_apps_not_every_module(catalogue):
    """Decision 17 of the catalog spec (round 16): premium apps go with the paid plans, so no card says
    «all modules»; Free promises the free apps and Starter (the first paid plan) every app, free and premium —
    what the hero of /pricing/ already promises (2026-10-15)."""
    free = catalogue["free"]
    assert "All free apps included" in free.features_en
    assert "Todas las apps gratuitas incluidas" in free.features_es
    starter = catalogue["starter"]
    assert "All apps included, free and premium" in starter.features_en
    assert "Todas las apps incluidas, gratuitas y premium" in starter.features_es
    for plan in catalogue.values():
        lines = [line.lower() for line in [*plan.features_en, *plan.features_es]]
        assert not any("all modules" in line or "todos los módulos" in line for line in lines), plan.slug


def test_db_limits_match_the_round_9_decision(catalogue):
    """PLAN §14.2 (Ioan): Free runs 1 transaction at a time per hub and process with a 5 s
    ``statement_timeout``; a paid plan, 3 and 15 s. Since 2026-10-15 (Ioan) each plan up doubles the
    resources of the one below: Standard, 6 and 15 s. They travel in the hub's state snapshot
    (PLAN-SAAS §2.2) and the Hub enforces them with a semaphore per hub."""
    expected = {slug: (3, 15) for slug in catalogue}
    expected["free"] = (1, 5)
    expected["standard"] = (6, 15)
    # The upgrade-only tiers go on doubling (Ioan, 2026-10-15): Pro, Enterprise and Max.
    expected.update({"pro": (12, 15), "enterprise": (24, 15), "max": (48, 15)})
    actual = {
        slug: (plan.max_db_connections, plan.statement_timeout_seconds)
        for slug, plan in catalogue.items()
    }
    assert actual == expected


def test_each_plan_up_doubles_the_resources_of_the_one_below_and_says_so(catalogue):
    """Ioan, 2026-10-15: what grows from one plan to the next is the AI messages and the «resources», which are the
    database's input/output capacity. Free is sized for one device; Starter has the full tier for several
    devices; Standard twice Starter. The cards say it as database throughput, in words: no engine name, no
    connection count, no timeout."""
    free, starter, standard = (catalogue[s] for s in ("free", "starter", "standard"))
    assert standard.max_db_connections == 2 * starter.max_db_connections
    assert free.max_db_connections < starter.max_db_connections
    assert "Basic database throughput, sized for one device" in free.features_en
    assert "Capacidad de base de datos básica, a la medida de un dispositivo" in free.features_es
    assert "Full database throughput, for several devices at once" in starter.features_en
    assert "Capacidad de base de datos completa, para varios dispositivos a la vez" in starter.features_es
    assert any(f.startswith("Twice the database throughput of Starter") for f in standard.features_en), standard.features_en
    assert any(f.startswith("El doble de capacidad de base de datos que Starter") for f in standard.features_es), (
        standard.features_es
    )
    for plan in catalogue.values():
        for text in _copy(plan):
            assert not re.search(r"\b[1-9]\d*\s*(transactions?|connections?|conexiones|transacciones)\b", text, re.I), text
            assert not re.search(r"\b(connections?|conexiones|timeout|statement)\b", text, re.I), text
    with translation.override("en"):
        assert [p.resources_label for p in (free, starter, standard)] == [
            "Basic, for one device", "Full, for several devices", "Double",
        ]


#: The ladder from Starter up, each plan twice the one below (Ioan, 2026-10-15), and the line its card says it with.
LADDER = (
    ("starter", "Full database throughput", "Capacidad de base de datos completa"),
    ("standard", "Twice the database throughput of Starter", "El doble de capacidad de base de datos que Starter"),
    ("pro", "Four times the database throughput of Starter", "El cuádruple de capacidad de base de datos que Starter"),
    ("enterprise", "Eight times the database throughput of Starter", "Ocho veces la capacidad de base de datos de Starter"),
    ("max", "Sixteen times the database throughput of Starter", "Dieciséis veces la capacidad de base de datos de Starter"),
)


def test_from_starter_up_each_plan_doubles_the_one_below(catalogue):
    """Ioan, 2026-10-15: the upgrade-only tiers go on up the same ladder (PLAN §14.2), all at 15 s."""
    for (lower, *_), (upper, *_) in zip(LADDER, LADDER[1:], strict=False):
        assert catalogue[upper].max_db_connections == 2 * catalogue[lower].max_db_connections, upper
        assert catalogue[upper].statement_timeout_seconds == 15, upper


def test_every_paid_card_says_its_rung_of_the_ladder_in_words(catalogue):
    """One line per card, on the same scale, in both languages; the upgrade-only tiers keep «Everything in …»."""
    for slug, english, spanish in LADDER:
        plan = catalogue[slug]
        assert sum(line.startswith(english) for line in plan.features_en) == 1, (slug, plan.features_en)
        assert sum(line.startswith(spanish) for line in plan.features_es) == 1, (slug, plan.features_es)
    for slug, below in (("pro", "Standard"), ("enterprise", "Pro"), ("max", "Enterprise")):
        assert catalogue[slug].features_en[0] == f"Everything in {below}", slug


def test_a_plan_sizes_no_infrastructure():
    """PLAN-SAAS §1: without a container per hub, a plan has no CPU, memory, storage nor paused price."""
    assert {field.name for field in Plan._meta.get_fields()} == PLAN_FIELDS


def test_the_seat_cap_is_the_number_the_free_card_promises(catalogue):
    """saas#2022: the cap that is ENFORCED has to be the one that was SOLD."""
    free = catalogue["free"]
    assert free.max_users == 3, f"free plan caps users at {free.max_users}"
    promises = [f for f in free.features_en if "3" in f and "user" in f.lower()]
    promises += [f for f in free.features_es if "3" in f and "usuario" in f.lower()]
    assert promises, (
        f"free plan no longer promises a user count: {free.features_en} / {free.features_es}"
    )


#: How many modules a business may choose to turn on, by plan (2026-10-24): every module is on every plan; a plan caps
#: only the ones the business picks (``max_apps``), never what they require. Free 15, each plan up doubles the one
#: below; the upgrade-only tiers have no cap (0); ``payment-test`` reads as Starter.
EXPECTED_MAX_APPS = {
    "free": 15,
    "starter": 30,
    "standard": 60,
    "pro": 0,
    "enterprise": 0,
    "max": 0,
    PAYMENT_TEST: 30,
}
#: The modules a business on the biggest vertical template chooses (its roots, the ones no other module of it
#: requires: the restaurant's 13 on the Hub's main of 2026-10-24, ``website`` included) and the one on its way into it
#: (``tip``): no plan on sale caps below them.
BIGGEST_TEMPLATE_ROOTS = 13 + 1


def test_each_plan_caps_the_modules_a_business_chooses_to_turn_on(catalogue):
    assert {slug: plan.max_apps for slug, plan in catalogue.items()} == EXPECTED_MAX_APPS


def test_each_plan_on_sale_doubles_the_modules_of_the_one_below(catalogue):
    free, starter, standard = (catalogue[slug].max_apps for slug in ("free", "starter", "standard"))

    assert (starter, standard) == (2 * free, 2 * starter)


def test_no_plan_on_sale_caps_below_what_the_biggest_template_chooses(catalogue):
    """A business born on the biggest vertical's template can still turn on every module it came with, and more."""
    for slug in ("free", "starter", "standard"):
        assert catalogue[slug].max_apps > BIGGEST_TEMPLATE_ROOTS, slug


def test_a_new_plan_caps_no_modules(db):
    """0 is «no limit»: a plan staff add in the admin lets a business turn on every module until they set a figure."""
    plan = Plan.objects.create(slug="bare", name_en="Bare", price_monthly=Decimal("9.99"))

    assert plan.max_apps == 0


def test_paid_plans_do_not_cap_people(catalogue):
    """ "Every location, device and user included" is the paid promise (saas#1760)."""
    for slug in ("starter", "standard", "pro", "enterprise", "max"):
        assert catalogue[slug].max_users == 0, (
            f"[{slug}] paid plans must not cap users"
        )


# saas#1955: the two axes /pricing/ compares on. ADR-0474 fixes the module tier and ADR-0426
# the support ladder. slug → (included_level, support_level, includes_custom_domain)
#: Messages a month each plan includes (Ioan, 2026-10-15; ADR-0474 for Free and Starter): one request of the
#: user to the assistant is one message; WhatsApp has its own count. Standard doubles Starter (each plan up
#: doubles the one below); ``payment-test`` reads as Starter. 0 would mean none, never «unlimited».
EXPECTED_MONTHLY_MESSAGES = {
    "free": (30, 30),
    "starter": (300, 150),
    "standard": (600, 300),
    # The upgrade-only tiers: the old stack's levels pro and enterprise (ADR-0474).
    "pro": (1000, 500),
    "enterprise": (3000, 800),
    "max": (3000, 800),
    PAYMENT_TEST: (300, 150),
}


def test_each_plan_includes_its_monthly_assistant_and_whatsapp_messages(catalogue):
    actual = {
        slug: (plan.assistant_messages_per_month, plan.whatsapp_messages_per_month)
        for slug, plan in catalogue.items()
    }

    assert actual == EXPECTED_MONTHLY_MESSAGES


def test_standard_includes_twice_the_messages_of_starter(catalogue):
    starter, standard = catalogue["starter"], catalogue["standard"]

    assert standard.assistant_messages_per_month == 2 * starter.assistant_messages_per_month
    assert standard.whatsapp_messages_per_month == 2 * starter.whatsapp_messages_per_month


def test_a_plan_without_a_figure_includes_no_messages(db):
    """0 is «none»: a plan staff adds in the admin includes nothing until they say how many."""
    plan = Plan.objects.create(slug="bare", name_en="Bare", price_monthly=Decimal("9.99"))

    assert (plan.assistant_messages_per_month, plan.whatsapp_messages_per_month) == (0, 0)


#: What one message costs us at most, net (ADR-0474, saas#1952): the model's tokens of one assistant request, and
#: Meta's dearest billable WhatsApp message (marketing, Spain).
ASSISTANT_COST_PER_MESSAGE = Decimal("0.02")
WHATSAPP_COST_PER_MESSAGE = Decimal("0.0509")
#: The share of a paid plan's net monthly price left when its customer uses up both quotas (Ioan's condition:
#: never pay the model provider or Meta more than half of what the plan charges).
MIN_MARGIN_PERCENT = 50


def _paid_plans(catalogue):
    """The plans a customer pays for: Free is the permanent floor (ADR-0154) and ``payment-test`` is staff-only
    (saas#1052), so neither has a price the margin can be taken from."""
    return [plan for plan in catalogue.values() if plan.price_monthly > 0 and not plan.internal_only]


def test_a_paid_plan_keeps_half_its_price_when_its_messages_are_used_up(catalogue):
    """ADR-0474 (saas#1952): the net monthly price pays for a customer that burns the whole quota of both, and
    still keeps at least half of it. Assistant at its cost per message; WhatsApp at Meta's dearest rate."""
    for plan in _paid_plans(catalogue):
        worst_case = (
            plan.assistant_messages_per_month * ASSISTANT_COST_PER_MESSAGE
            + plan.whatsapp_messages_per_month * WHATSAPP_COST_PER_MESSAGE
        )

        assert worst_case * 100 <= plan.price_monthly * (100 - MIN_MARGIN_PERCENT), (plan.slug, worst_case)


def test_the_margin_check_reads_every_paid_plan_at_its_real_cost(catalogue):
    """A plan slipping out of the check or a cost rounded to zero must be noticed."""
    assert {plan.slug for plan in _paid_plans(catalogue)} == {"starter", "standard", *UPGRADE_ONLY}
    assert (ASSISTANT_COST_PER_MESSAGE, WHATSAPP_COST_PER_MESSAGE) == (Decimal("0.02"), Decimal("0.0509"))


def test_the_margin_check_catches_a_plan_that_gives_away_too_many_messages():
    """Positive control: Starter's price with ten times its messages would leave less than half."""
    worst_case = 3000 * ASSISTANT_COST_PER_MESSAGE + 1500 * WHATSAPP_COST_PER_MESSAGE

    assert worst_case * 100 > Decimal("29.99") * (100 - MIN_MARGIN_PERCENT)


EXPECTED_COMMERCIAL_LADDER = {
    "free": ("free", "community", False),
    "starter": ("basic", "email", False),
    "standard": ("basic", "priority_email", True),
    "pro": ("pro", "priority_email", True),
    "enterprise": ("enterprise", "contract", True),
    "max": ("enterprise", "contract", True),
}


def test_commercial_ladder_matches_adr_0474_and_adr_0426(catalogue):
    """The ladder is a contract, not a default: both columns default to the bottom rung."""
    for slug, (included, support, custom_domain) in EXPECTED_COMMERCIAL_LADDER.items():
        plan = catalogue[slug]
        assert plan.included_level == included, (
            f"[{slug}] included tier drifted from ADR-0474: {plan.included_level!r}"
        )
        assert plan.support_level == support, (
            f"[{slug}] support tier drifted from ADR-0426: {plan.support_level!r}"
        )
        assert plan.includes_custom_domain is custom_domain, (
            f"[{slug}] custom-domain gate drifted from the 2026-09-09 decision: {plan.includes_custom_domain!r}"
        )


def test_every_public_plan_has_a_declared_position_on_both_ladders(catalogue):
    """A plan added tomorrow cannot reach /pricing/ without a commercial position."""
    public = {slug for slug, plan in catalogue.items() if not plan.internal_only}

    undeclared = public - set(EXPECTED_COMMERCIAL_LADDER)
    assert not undeclared, (
        f"public plans with no declared module/support tier: {sorted(undeclared)}"
    )

    vanished = set(EXPECTED_COMMERCIAL_LADDER) - public
    assert not vanished, (
        f"the ladder pins plans the catalogue no longer has: {sorted(vanished)}"
    )


# saas#1956, ADR-0426: what we publish is what a customer can reclaim.
UNLIMITED_API_PATTERNS = [
    (r"no usage limits", "unmetered API claim"),
    (r"sin l[ií]mites de uso", "unmetered API claim (es)"),
    (r"unlimited API", "unmetered API claim"),
    (r"API ilimitada", "unmetered API claim (es)"),
]


def test_no_plan_promises_an_api_the_limiter_does_not_deliver(catalogue):
    for slug, plan in catalogue.items():
        for text in _copy(plan):
            for pattern, label in UNLIMITED_API_PATTERNS:
                assert not re.search(pattern, text, re.I), (
                    f"[{slug}] {label} in commercial copy: {text!r}"
                )


def test_the_api_patterns_catch_the_lines_that_were_actually_published():
    """Positive control: these are the exact strings the seed carried before saas#1956."""
    for published in (
        "Full API with no usage limits",
        "API completa sin límites de uso",
    ):
        assert any(
            re.search(pattern, published, re.I) for pattern, _ in UNLIMITED_API_PATTERNS
        ), f"guard is blind to the claim it exists to stop: {published!r}"


def test_custom_domain_is_only_promised_by_the_plans_that_gate_it(catalogue):
    """The card and the door have to agree (saas#1956)."""
    sellers = []
    for slug, plan in catalogue.items():
        promises = [f for f in plan.features_en if "custom domain" in f.lower()]
        if promises:
            sellers.append(slug)
            assert plan.includes_custom_domain, (
                f"[{slug}] sells {promises!r} but the gate refuses it"
            )
    assert "standard" in sellers, (
        "no card mentions a custom domain any more — this guard went blind"
    )


# --- From test_plan_trial_label.py (saas#2424) ------------------------------------------------


def test_no_plan_types_the_trial_as_a_feature(catalogue):
    """Cards paint the trial from ``trial_period_days`` (``Plan.trial_label``), never from a feature."""
    for plan in catalogue.values():
        for feature in [*plan.features_en, *plan.features_es]:
            assert "trial" not in feature.lower(), (
                f"[{plan.slug}] carries the trial as a feature: {feature!r}"
            )
            assert "prueba gratis" not in feature.lower(), (
                f"[{plan.slug}] carries the trial as a feature: {feature!r}"
            )


# --- From test_payment_test_plan.py (saas#1052) -----------------------------------------------


def test_the_catalogue_has_the_payment_test_plan(catalogue):
    assert PAYMENT_TEST in catalogue


def test_the_payment_test_plan_has_no_trial(catalogue):
    """Its reason to exist: with a trial the first charge is 0 € and there is no invoice."""
    plan = catalogue[PAYMENT_TEST]
    assert plan.trial_period_days == 0
    assert plan.has_trial() is False


def test_the_payment_test_price_breaks_down_cleanly_into_base_and_vat(catalogue):
    """1.00 € net → 1.21 € charged to a Spanish customer: prices are net (saas#1098)."""
    assert catalogue[PAYMENT_TEST].price_monthly == Decimal("1.00")


def test_the_payment_test_plan_is_marked_internal(catalogue):
    assert catalogue[PAYMENT_TEST].internal_only is True


# --- The catalogue of 2026-10-15: three plans on sale at sign-up, the upgrade-only tiers kept ---------------------


def test_the_upgrade_only_tiers_are_kept_active_above_the_plans_on_sale(catalogue):
    """Ioan, 2026-10-15: Pro, Enterprise and Max are not retired. They stay active and ``upgrade_only``: the Store
    offers them to a business that already pays, and the public web lists only the plans a visitor signs up for."""
    for slug in UPGRADE_ONLY:
        plan = catalogue[slug]
        assert (plan.is_active, plan.upgrade_only, plan.internal_only) == (True, True, False), slug
        assert plan.price_monthly > catalogue["standard"].price_monthly, slug
