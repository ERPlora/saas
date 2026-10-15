"""Guard tests for ``sync_hub_plans``: the seed creates the plan catalogue, and the admin owns it after.

It runs in the ``saas-migrate`` task on every deploy, so by default it only creates the plans missing by
``slug`` and never overwrites what staff edited in the admin; ``--update`` puts every field back to the
seed (the old behaviour).

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
- ``TestTheCapReachesProductionOnItsOwn`` (3) and
  ``test_the_deploy_migration_and_the_seed_declare_the_same_ladder`` pinned the data migrations
  ``0029``/``0031`` that patched the rows already in production. saas-next starts from an empty
  database, so there is no live row to patch and no migration to pin against the seed.
"""

import re
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from hubs.management.commands.sync_hub_plans import PLANS
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
    "created_at", "updated_at",
    # The reverse relation of Subscription.plan (the hubs on the plan), not a column of the plan.
    "subscriptions",
}  # fmt: skip

PAYMENT_TEST = "payment-test"


def _sync(*args) -> str:
    out = StringIO()
    call_command("sync_hub_plans", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def seeded_plans():
    _sync()
    return {p.slug: p for p in Plan.objects.all()}


def test_starter_english_fields_are_english(seeded_plans):
    starter = seeded_plans["starter"]
    assert (
        starter.description_en
        == "Your business in the cloud. No servers, no maintenance, always available."
    )
    assert "Unlimited users" in starter.features_en
    assert "Fully managed cloud" in starter.features_en
    for feature in starter.features_en:
        for marker in SPANISH_MARKERS:
            assert marker not in feature, (
                f"Spanish marker {marker!r} leaked into EN feature {feature!r}"
            )


def test_spanish_mirror_is_preserved(seeded_plans):
    starter = seeded_plans["starter"]
    assert (
        starter.description_es
        == "Tu negocio en la nube. Sin servidores, sin mantenimiento, siempre disponible."
    )
    assert "Usuarios ilimitados" in starter.features_es
    assert "Cloud gestionado" in starter.features_es


def test_recommended_badge_is_translated(seeded_plans):
    standard = seeded_plans["standard"]
    assert standard.featured_label_en == "Recommended"
    assert standard.featured_label_es == "Recomendado"


def test_support_copy_never_promises_a_clock_we_do_not_run(seeded_plans):
    """saas#1760: support is sold as CHANNEL + PRIORITY, never as an unmeasured clock."""
    for slug, plan in seeded_plans.items():
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


def test_support_ladder_still_differentiates_by_channel_and_priority(seeded_plans):
    """Removing the fake clock must not flatten the ladder into 'support' everywhere."""
    assert any(f == "Community support" for f in seeded_plans["free"].features_en)
    assert any("Email support" in f for f in seeded_plans["starter"].features_en)
    assert any(
        "Priority email support" in f for f in seeded_plans["standard"].features_en
    )
    assert any(f == "Soporte de la comunidad" for f in seeded_plans["free"].features_es)
    assert any("Soporte por email" in f for f in seeded_plans["starter"].features_es)
    assert any("prioritario" in f for f in seeded_plans["standard"].features_es)


def test_no_english_field_contains_spanish(seeded_plans):
    """Sweep every plan: the English description and features are Spanish-free."""
    for slug, plan in seeded_plans.items():
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


def test_no_plan_sells_infrastructure_specs(seeded_plans):
    """saas#1760: commercial copy sells the HUB, never the box it runs on."""
    for slug, plan in seeded_plans.items():
        for text in _copy(plan):
            for pattern, label in INFRA_SPEC_PATTERNS:
                assert not re.search(pattern, text, re.I), (
                    f"[{slug}] {label} in commercial copy: {text!r}"
                )


def test_no_plan_publishes_an_uptime_sla_percentage(seeded_plans):
    """saas#1760: the only availability statement is the one in the terms (99.5 %, reasonable efforts)."""
    for slug, plan in seeded_plans.items():
        for text in _copy(plan):
            assert not re.search(r"\d{2}[.,]\d+\s*%", text), (
                f"[{slug}] uptime SLA claim in plan copy: {text!r}"
            )
            assert "SLA" not in text, f"[{slug}] SLA claim in plan copy: {text!r}"


def test_subscription_unit_is_the_hub(seeded_plans):
    """saas#1760: one subscription buys ONE hub, with every location and device in it. The copy calls it what the
    panel calls it, a business (audit 2 S-12: «Precio por hub» in the Store was the Hub's word)."""
    for slug in ("starter", "standard"):
        plan = seeded_plans[slug]
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


def test_recovery_window_is_the_same_on_every_plan(seeded_plans):
    """saas#1760 + infra#136: the backup window is physical and common to the cluster."""
    backup_lines_en = {
        line
        for plan in seeded_plans.values()
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
#: downloads page (``public/templates/public/downloads.html``).
MANAGED_DATABASE = {
    "en": "Managed database, with continuous backups and point-in-time recovery for 14 days",
    "es": "Base de datos gestionada, con copias de seguridad continuas y recuperación a cualquier momento de los últimos 14 días",
}
#: Ioan's rule for the public web: the copy sells what the customer gets, never the technology under it.
TECHNOLOGY_NAMES = ("postgresql", "postgres", "aurora")


def _names_a_technology(text: str) -> bool:
    return any(name in text.lower() for name in TECHNOLOGY_NAMES)


def test_no_plan_names_the_technology_under_it(seeded_plans):
    for slug, plan in seeded_plans.items():
        for text in _copy(plan):
            assert not _names_a_technology(text), f"[{slug}] technology name in plan copy: {text!r}"


def test_the_technology_guard_catches_the_lines_that_were_actually_published():
    """Positive control: the database lines the seed carried before the rule."""
    for published in ("Managed PostgreSQL database", "Base de datos PostgreSQL gestionada"):
        assert _names_a_technology(published), published


def test_the_database_and_its_backups_are_one_line(seeded_plans):
    """«Managed database» and «continuous backups» are one sentence, not two lines saying backups twice."""
    for slug in ("free", "starter"):
        plan = seeded_plans[slug]
        assert MANAGED_DATABASE["en"] in plan.features_en, slug
        assert MANAGED_DATABASE["es"] in plan.features_es, slug
    for plan in seeded_plans.values():
        assert sum("backup" in line.lower() for line in plan.features_en) <= 1, plan.slug
        assert sum("copias" in line.lower() for line in plan.features_es) <= 1, plan.slug


def test_the_recovery_window_is_the_one_aurora_keeps(seeded_plans):
    """The card promises the 14 days Aurora keeps (``backup_retention_period = 14``,
    ``aws-next/stacks/prod/aurora.tf``), no more: the old «up to 30 days» was the old cluster's
    (the public web's session, 2026-10-14)."""
    english = {
        line
        for plan in seeded_plans.values()
        for line in plan.features_en
        if "backup" in line.lower()
    }
    spanish = {
        line
        for plan in seeded_plans.values()
        for line in plan.features_es
        if "copias" in line.lower()
    }

    assert english == {MANAGED_DATABASE["en"]}
    assert spanish == {MANAGED_DATABASE["es"]}
    assert not any(
        "30" in line
        for plan in seeded_plans.values()
        for line in [*plan.features_en, *plan.features_es]
    )


def test_the_plans_promise_the_free_apps_not_every_module(seeded_plans):
    """Decision 17 of the catalog spec (round 16): premium apps go with the paid plans, so no card says
    «all modules»; Free and Starter promise the free apps."""
    for slug in ("free", "starter"):
        plan = seeded_plans[slug]
        assert "All free apps included" in plan.features_en, slug
        assert "Todas las apps gratuitas incluidas" in plan.features_es, slug
    for plan in seeded_plans.values():
        lines = [line.lower() for line in [*plan.features_en, *plan.features_es]]
        assert not any("all modules" in line or "todos los módulos" in line for line in lines), plan.slug


def test_db_limits_match_the_round_9_decision(seeded_plans):
    """PLAN §14.2 (Ioan): Free runs 1 transaction at a time per hub and process with a 5 s
    ``statement_timeout``; every paid plan, 3 and 15 s. They travel in the hub's state snapshot
    (PLAN-SAAS §2.2) and the Hub enforces them with a semaphore per hub."""
    expected = {slug: (3, 15) for slug in seeded_plans}
    expected["free"] = (1, 5)
    actual = {
        slug: (plan.max_db_connections, plan.statement_timeout_seconds)
        for slug, plan in seeded_plans.items()
    }
    assert actual == expected


def test_a_plan_sizes_no_infrastructure():
    """PLAN-SAAS §1: without a container per hub, a plan has no CPU, memory, storage nor paused price;
    and the seed writes only fields the plan has."""
    assert {field.name for field in Plan._meta.get_fields()} == PLAN_FIELDS
    for plan in PLANS:
        assert set(plan) <= PLAN_FIELDS - {"subscriptions"}, plan["slug"]


def test_the_seat_cap_is_the_number_the_free_card_promises(seeded_plans):
    """saas#2022: the cap that is ENFORCED has to be the one that was SOLD."""
    free = seeded_plans["free"]
    assert free.max_users == 3, f"free plan caps users at {free.max_users}"
    promises = [f for f in free.features_en if "3" in f and "user" in f.lower()]
    promises += [f for f in free.features_es if "3" in f and "usuario" in f.lower()]
    assert promises, (
        f"free plan no longer promises a user count: {free.features_en} / {free.features_es}"
    )


def test_paid_plans_do_not_cap_people(seeded_plans):
    """ "Every location, device and user included" is the paid promise (saas#1760)."""
    for slug in ("starter", "standard", "pro", "enterprise", "max"):
        assert seeded_plans[slug].max_users == 0, (
            f"[{slug}] paid plans must not cap users"
        )


# saas#1955: the two axes /pricing/ compares on. ADR-0474 fixes the module tier and ADR-0426
# the support ladder. slug → (included_level, support_level, includes_custom_domain)
EXPECTED_COMMERCIAL_LADDER = {
    "free": ("free", "community", False),
    "starter": ("basic", "email", False),
    "standard": ("basic", "priority_email", True),
    "pro": ("pro", "priority_email", True),
    "enterprise": ("enterprise", "contract", True),
    "max": ("enterprise", "contract", True),
}


def test_commercial_ladder_matches_adr_0474_and_adr_0426(seeded_plans):
    """The ladder is a contract, not a default: both columns default to the bottom rung."""
    for slug, (included, support, custom_domain) in EXPECTED_COMMERCIAL_LADDER.items():
        plan = seeded_plans[slug]
        assert plan.included_level == included, (
            f"[{slug}] included tier drifted from ADR-0474: {plan.included_level!r}"
        )
        assert plan.support_level == support, (
            f"[{slug}] support tier drifted from ADR-0426: {plan.support_level!r}"
        )
        assert plan.includes_custom_domain is custom_domain, (
            f"[{slug}] custom-domain gate drifted from the 2026-09-09 decision: {plan.includes_custom_domain!r}"
        )


def test_every_public_plan_has_a_declared_position_on_both_ladders(seeded_plans):
    """A plan added tomorrow cannot reach /pricing/ without a commercial position."""
    public = {slug for slug, plan in seeded_plans.items() if not plan.internal_only}

    undeclared = public - set(EXPECTED_COMMERCIAL_LADDER)
    assert not undeclared, (
        f"public plans with no declared module/support tier: {sorted(undeclared)}"
    )

    vanished = set(EXPECTED_COMMERCIAL_LADDER) - public
    assert not vanished, (
        f"the ladder pins plans the seed no longer creates: {sorted(vanished)}"
    )


# saas#1956, ADR-0426: what we publish is what a customer can reclaim.
UNLIMITED_API_PATTERNS = [
    (r"no usage limits", "unmetered API claim"),
    (r"sin l[ií]mites de uso", "unmetered API claim (es)"),
    (r"unlimited API", "unmetered API claim"),
    (r"API ilimitada", "unmetered API claim (es)"),
]


def test_no_plan_promises_an_api_the_limiter_does_not_deliver(seeded_plans):
    for slug, plan in seeded_plans.items():
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


def test_custom_domain_is_only_promised_by_the_plans_that_gate_it(seeded_plans):
    """The card and the door have to agree (saas#1956)."""
    sellers = []
    for slug, plan in seeded_plans.items():
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


def test_the_seed_does_not_type_the_trial_as_a_feature(seeded_plans):
    """Cards paint the trial from ``trial_period_days`` (``Plan.trial_label``), never from a feature."""
    for plan in seeded_plans.values():
        for feature in [*plan.features_en, *plan.features_es]:
            assert "trial" not in feature.lower(), (
                f"[{plan.slug}] seeds the trial as a feature: {feature!r}"
            )
            assert "prueba gratis" not in feature.lower(), (
                f"[{plan.slug}] seeds the trial as a feature: {feature!r}"
            )


# --- From test_payment_test_plan.py (saas#1052) -----------------------------------------------


def test_seed_creates_the_payment_test_plan(seeded_plans):
    assert PAYMENT_TEST in seeded_plans


def test_the_payment_test_plan_has_no_trial(seeded_plans):
    """Its reason to exist: with a trial the first charge is 0 € and there is no invoice."""
    plan = seeded_plans[PAYMENT_TEST]
    assert plan.trial_period_days == 0
    assert plan.has_trial() is False


def test_the_payment_test_price_breaks_down_cleanly_into_base_and_vat(seeded_plans):
    """1.00 € net → 1.21 € charged to a Spanish customer: prices are net (saas#1098)."""
    assert seeded_plans[PAYMENT_TEST].price_monthly == Decimal("1.00")


def test_the_payment_test_plan_is_marked_internal(seeded_plans):
    assert seeded_plans[PAYMENT_TEST].internal_only is True


def test_seed_is_idempotent(seeded_plans):
    first = list(
        Plan.objects.values_list("slug", "is_active", "price_monthly").order_by("slug")
    )
    _sync()

    assert (
        list(
            Plan.objects.values_list("slug", "is_active", "price_monthly").order_by(
                "slug"
            )
        )
        == first
    )
    assert len(first) == len(PLANS) == 7


def _edit_starter_in_the_admin():
    Plan.objects.filter(slug="starter").update(price_monthly=Decimal("1"), name_es="Otro")


def _starter():
    starter = Plan.objects.get(slug="starter")
    return starter.price_monthly, starter.name_es


def test_seed_keeps_a_plan_edited_in_the_admin(seeded_plans):
    """Every deploy runs the seed: without ``--update`` it never overwrites what staff edited."""
    _edit_starter_in_the_admin()

    out = _sync()

    assert _starter() == (Decimal("1"), "Otro")
    assert "0 created, 7 existing" in out


def test_seed_with_update_overwrites_a_plan_edited_in_the_admin(seeded_plans):
    """``--update`` is the old behaviour: the seed puts every field of every plan back."""
    _edit_starter_in_the_admin()

    out = _sync("--update")

    assert _starter() == (Decimal("29.99"), "Starter")
    assert "0 created, 7 updated" in out


def test_seed_creates_only_the_missing_plans(seeded_plans):
    Plan.objects.filter(slug="pro").delete()
    _edit_starter_in_the_admin()

    out = _sync()

    assert Plan.objects.get(slug="pro").price_monthly == Decimal("109.99")
    assert _starter() == (Decimal("1"), "Otro")
    assert "1 created, 6 existing" in out


def test_seed_on_an_empty_database_creates_the_whole_catalogue():
    out = _sync()

    assert Plan.objects.count() == len(PLANS) == 7
    assert "7 created, 0 existing" in out
