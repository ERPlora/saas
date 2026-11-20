"""The words of the plan cards the data migrations of hubs rewrite: no infrastructure on the paid cards (0020),
what every plan on sale gives (0021), no custom domain nobody can connect (0026) and what a recovery keeps
(0029)."""

import re
from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.core.management import call_command

from hubs.tests.data_migrations import (
    CARDS_0013,
    CATALOGUE_0013,
    COPY_0020,
    COPY_0021,
    COPY_0026,
    COPY_0029,
    DATABASE_LINE_PLANS,
    FEATURES_0026,
    LINES_0013,
    LINES_0021,
    LINES_0029,
    _expected_0013,
    _imported_modules,
    _row,
    _SchemaEditor,
    _snapshot,
)
from hubs.tests.test_plan_catalogue import promises_a_recovery_without_what_it_keeps

# --- 0020: the paid cards stop promising infrastructure --------------------------------------------


PLAN_COPY = "0020_paid_plan_copy"
#: The words of a paid card that promise infrastructure the plans no longer sell and nobody runs, in both
#: languages; the support «agreed in contract» is Enterprise's and Max's real ``support_level`` and stays.
INFRASTRUCTURE_WORDS = (
    "dedicated", "isolated", "autoscal", "disaster", "monitoring", "single-node", "infrastructure",
    "dedicada", "aislada", "autoescalado", "desastres", "monitoreo", "un solo nodo", "infraestructura",
)  # fmt: skip
#: What 0013 seeded in those same columns, and 0020 gives back on reverse.
COPY_0013 = {slug: {column: CATALOGUE_0013[slug][column] for column in columns} for slug, columns in COPY_0020.items()}
#: Every column 0020 writes, as ``(plan, column)``.
CARD_COLUMNS = [(slug, column) for slug, columns in COPY_0020.items() for column in columns]


def _plan_copy():
    return import_module(f"hubs.migrations.{PLAN_COPY}")


def _forward():
    _plan_copy().describe_what_the_plans_give(global_apps, _SchemaEditor())


def _backward():
    _plan_copy().give_back_the_words_of_0013(global_apps, _SchemaEditor())


def _cards_of(Plan) -> dict[str, dict]:
    return {slug: _row(Plan.objects.get(slug=slug), columns) for slug, columns in COPY_0020.items()}


def _edited(column: str):
    return ["Edited by staff"] if column.startswith("features") else "Edited by staff"


@pytest.mark.django_db
class TestThePaidCardsStopPromisingInfrastructure:
    """The Store shows a paid plan's description and features to a business that already pays; from 0020 they say
    what the plan gives and nothing it does not. Only the columns of COPY_0020 move, each only while it still reads
    0013's words: what staff wrote in the admin is theirs. The plans, their prices and their limits stay."""

    @pytest.fixture
    def seeded_cards(self, plans):
        from hubs.models import Plan

        for slug, columns in COPY_0013.items():
            Plan.objects.filter(slug=slug).update(**columns)
        return Plan

    def test_the_0013_words_are_the_ones_that_promised_infrastructure(self):
        for slug, columns in COPY_0013.items():
            text = " ".join(" ".join(value) if isinstance(value, list) else value for value in columns.values())
            assert any(word in text.lower() for word in INFRASTRUCTURE_WORDS), slug

    def test_each_card_reads_what_its_plan_gives(self, seeded_cards):
        _forward()

        assert _cards_of(seeded_cards) == COPY_0020

    def test_nothing_but_those_columns_moves(self, seeded_cards):
        before = _snapshot(seeded_cards)

        _forward()

        after = _snapshot(seeded_cards)
        assert {slug: row for slug, row in after.items() if slug not in COPY_0020} == {
            slug: row for slug, row in before.items() if slug not in COPY_0020
        }
        for slug, columns in COPY_0020.items():
            assert after[slug] == {**before[slug], **columns}, slug

    @pytest.mark.parametrize(("slug", "column"), CARD_COLUMNS)
    def test_a_column_staff_rewrote_is_theirs(self, seeded_cards, slug, column):
        seeded_cards.objects.filter(slug=slug).update(**{column: _edited(column)})

        _forward()

        expected = {plan: dict(columns) for plan, columns in COPY_0020.items()}
        expected[slug][column] = _edited(column)
        assert _cards_of(seeded_cards) == expected

    def test_reversing_gives_back_the_words_of_0013(self, seeded_cards):
        _forward()
        _backward()

        assert _cards_of(seeded_cards) == COPY_0013

    @pytest.mark.parametrize(("slug", "column"), CARD_COLUMNS)
    def test_reversing_keeps_what_staff_wrote_after_it(self, seeded_cards, slug, column):
        _forward()
        seeded_cards.objects.filter(slug=slug).update(**{column: _edited(column)})

        _backward()

        expected = {plan: dict(columns) for plan, columns in COPY_0013.items()}
        expected[slug][column] = _edited(column)
        assert _cards_of(seeded_cards) == expected

    def test_it_is_idempotent_and_survives_a_database_without_the_rows(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug__in=COPY_0020).delete()
        for _ in range(2):
            _forward()
            _backward()

        assert not Plan.objects.filter(slug__in=COPY_0020).exists()

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        assert [name for name in _imported_modules(_plan_copy()) if name.startswith("hubs")] == []
        assert {slug: {column: old for column, (old, _) in columns.items()} for slug, columns in _plan_copy().COPY.items()} == COPY_0013
        assert {slug: {column: new for column, (_, new) in columns.items()} for slug, columns in _plan_copy().COPY.items()} == COPY_0020

    def test_the_new_words_promise_no_infrastructure(self):
        for slug, columns in COPY_0020.items():
            for value in columns.values():
                for text in value if isinstance(value, list) else [value]:
                    for word in INFRASTRUCTURE_WORDS:
                        assert word not in text.lower(), (slug, word, text)

    def test_the_new_words_are_what_the_rows_give(self):
        """Each claim of COPY_0020 against the seed of 0013: the throughput ladder, the messages, no cap, the support."""
        starter, pro, enterprise, top = (CATALOGUE_0013[slug] for slug in ("starter", "pro", "enterprise", "max"))
        connections = starter["max_db_connections"]

        assert pro["max_db_connections"] == 4 * connections
        assert enterprise["max_db_connections"] == 2 * pro["max_db_connections"] == 8 * connections
        assert top["max_db_connections"] == 16 * connections
        assert enterprise["assistant_messages_per_month"] > pro["assistant_messages_per_month"]
        assert enterprise["whatsapp_messages_per_month"] > pro["whatsapp_messages_per_month"]
        for plan in (pro, enterprise, top):
            assert (plan["max_devices"], plan["max_users"]) == (0, 0)
        assert (pro["support_level"], enterprise["support_level"], top["support_level"]) == (
            "priority_email", "contract", "contract",
        )
        # Max's named contact is a feature of its card that 0020 keeps.
        assert "Named technical contact agreed in contract" in top["features_en"]
        assert "max" not in [slug for slug, columns in COPY_0020.items() if "features_en" in columns]


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_paid_cards_and_forward_again():
    """``migrate hubs 0019`` and back: the cards read 0013's words again, then 0020's."""
    from hubs.models import Plan

    call_command("migrate", "hubs", "0019", verbosity=0)
    assert _cards_of(Plan) == COPY_0013

    call_command("migrate", "hubs", verbosity=0)
    assert _cards_of(Plan) == COPY_0020


# --- 0021: the cards on sale say what every plan gives ---------------------------------------------


CARDS_ON_SALE = "0021_plan_copy_on_sale"
#: Every column 0021 writes, as ``(plan, column)``.
ON_SALE_CARD_COLUMNS = [(slug, column) for slug, columns in COPY_0021.items() for column in columns]
#: «Location» and its Spanish words, as a card on sale must not name them.
LOCATION_WORDS = re.compile(r"\b(?:multi-?)?(?:locations?|locales?|sucursal(?:es)?|tiendas?)\b", re.IGNORECASE)
#: A tier of apps, as no card says it any more: every plan includes every module.
APP_TIER_WORDS = re.compile(r"\bpremium\b|\bfree apps\b|\bapps gratuitas\b", re.IGNORECASE)


def _cards_on_sale():
    return import_module(f"hubs.migrations.{CARDS_ON_SALE}")


def _forward_0021():
    _cards_on_sale().describe_the_cards_on_sale(global_apps, _SchemaEditor())


def _backward_0021():
    _cards_on_sale().give_back_the_words_of_0013(global_apps, _SchemaEditor())


def _cards_on_sale_of(Plan) -> dict[str, dict]:
    return {slug: _row(Plan.objects.get(slug=slug), columns) for slug, columns in COPY_0021.items()}


@pytest.mark.django_db
class TestTheCardsOnSaleSayWhatEveryPlanGives:
    """The cards of Free, Starter and Standard (the public web and the Store) said «every location included»,
    «several locations», «all free apps» and «free and premium»; from 0021 they say devices, users and every module,
    which is what the plans give. Only their features move, each column only while it still reads 0013's words: what
    staff wrote in the admin is theirs."""

    @pytest.fixture
    def seeded_cards(self, plans):
        from hubs.models import Plan

        for slug, columns in CARDS_0013.items():
            Plan.objects.filter(slug=slug).update(**columns)
        return Plan

    def test_the_lines_rewritten_are_exactly_the_0013_lines_that_named_a_location_or_a_tier_of_apps(self):
        rewritten = []
        for slug, columns in CARDS_0013.items():
            for column, lines in columns.items():
                named = [line for line in lines if LOCATION_WORDS.search(line) or APP_TIER_WORDS.search(line)]
                assert named, (slug, column)
                assert [line for line in named if line not in LINES_0021] == [], (slug, column)
                rewritten += [line for line in lines if line in LINES_0021]
        assert len(rewritten) == 10
        assert set(rewritten) == set(LINES_0021)

    def test_each_card_reads_what_its_plan_gives(self, seeded_cards):
        _forward_0021()

        assert _cards_on_sale_of(seeded_cards) == COPY_0021

    def test_the_new_lines_in_both_languages(self, seeded_cards):
        _forward_0021()

        free, starter, standard = (seeded_cards.objects.get(slug=slug) for slug in ("free", "starter", "standard"))
        assert standard.features_en[1:3] == [
            "Priced per business — every device and user included",
            "Twice the database throughput of Starter, for busy counters",
        ]
        assert standard.features_es[1:3] == [
            "Precio por negocio — con todos sus dispositivos y usuarios",
            "El doble de capacidad de base de datos que Starter, para mostradores con mucho movimiento",
        ]
        assert starter.features_en[0] == "Priced per business — every device and user included"
        assert starter.features_es[0] == "Precio por negocio — con todos sus dispositivos y usuarios"
        assert starter.features_en[4] == free.features_en[4] == "All apps included"
        assert starter.features_es[4] == free.features_es[4] == "Todas las apps incluidas"

    def test_nothing_but_those_columns_moves(self, seeded_cards):
        before = _snapshot(seeded_cards)

        _forward_0021()

        after = _snapshot(seeded_cards)
        assert {slug: row for slug, row in after.items() if slug not in COPY_0021} == {
            slug: row for slug, row in before.items() if slug not in COPY_0021
        }
        for slug, columns in COPY_0021.items():
            assert after[slug] == {**before[slug], **columns}, slug

    @pytest.mark.parametrize(("slug", "column"), ON_SALE_CARD_COLUMNS)
    def test_a_column_staff_rewrote_is_theirs(self, seeded_cards, slug, column):
        seeded_cards.objects.filter(slug=slug).update(**{column: ["Edited by staff"]})

        _forward_0021()

        expected = {plan: dict(columns) for plan, columns in COPY_0021.items()}
        expected[slug][column] = ["Edited by staff"]
        assert _cards_on_sale_of(seeded_cards) == expected

    def test_reversing_gives_back_the_words_of_0013(self, seeded_cards):
        _forward_0021()
        _backward_0021()

        assert _cards_on_sale_of(seeded_cards) == CARDS_0013

    @pytest.mark.parametrize(("slug", "column"), ON_SALE_CARD_COLUMNS)
    def test_reversing_keeps_what_staff_wrote_after_it(self, seeded_cards, slug, column):
        _forward_0021()
        seeded_cards.objects.filter(slug=slug).update(**{column: ["Edited by staff"]})

        _backward_0021()

        expected = {plan: dict(columns) for plan, columns in CARDS_0013.items()}
        expected[slug][column] = ["Edited by staff"]
        assert _cards_on_sale_of(seeded_cards) == expected

    def test_it_is_idempotent_and_survives_a_database_without_the_rows(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug__in=COPY_0021).delete()
        for _ in range(2):
            _forward_0021()
            _backward_0021()

        assert not Plan.objects.filter(slug__in=COPY_0021).exists()

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        copy = _cards_on_sale().COPY

        assert [name for name in _imported_modules(_cards_on_sale()) if name.startswith("hubs")] == []
        assert {slug: {column: old for column, (old, _) in columns.items()} for slug, columns in copy.items()} == CARDS_0013
        assert {slug: {column: new for column, (_, new) in columns.items()} for slug, columns in copy.items()} == COPY_0021

    def test_the_new_words_name_no_location_nor_a_tier_of_apps(self):
        for slug, columns in COPY_0021.items():
            for column, lines in columns.items():
                assert [line for line in lines if LOCATION_WORDS.search(line) or APP_TIER_WORDS.search(line)] == [], (
                    slug, column,
                )  # fmt: skip

    def test_free_never_named_a_location_and_only_its_module_line_moves(self):
        free = _expected_0013()["free"]
        texts = [free["description_en"], free["description_es"], *free["features_en"], *free["features_es"]]

        assert [text for text in texts if LOCATION_WORDS.search(text)] == []
        for column in ("features_en", "features_es"):
            changed = [(old, new) for old, new in zip(CARDS_0013["free"][column], COPY_0021["free"][column]) if old != new]
            assert len(changed) == 1, column

    def test_the_paid_tiers_above_name_no_tier_of_apps_so_0021_leaves_them(self):
        """Pro, Enterprise and Max (after 0020) and Standard's description never sold a tier of apps."""
        expected = _expected_0013()
        for slug in ("pro", "enterprise", "max", "standard"):
            row = {**expected[slug], **COPY_0020.get(slug, {})}
            texts = [row["description_en"], row["description_es"], *row["features_en"], *row["features_es"]]
            assert [text for text in texts if APP_TIER_WORDS.search(text)] == [], slug
        assert not {"pro", "enterprise", "max"} & set(_cards_on_sale().COPY)


@pytest.mark.django_db
def test_hubs_migrates_back_before_the_cards_on_sale_and_forward_again():
    """``migrate hubs 0020`` and back: Free, Starter and Standard read 0013's words again, then 0021's."""
    from hubs.models import Plan

    call_command("migrate", "hubs", "0020", verbosity=0)
    assert _cards_on_sale_of(Plan) == CARDS_0013

    call_command("migrate", "hubs", verbosity=0)
    # 0026 and 0029 run too: Standard's features end without the custom domain (saas#233), and the database line of
    # Free and Starter says what a recovery keeps (saas#408).
    assert _cards_on_sale_of(Plan) == {**COPY_0021, "standard": {**COPY_0021["standard"], **FEATURES_0026}, **COPY_0029}


# --- 0026: no card sells a custom domain nobody can connect ----------------------------------------


NO_CUSTOM_DOMAIN = "0026_no_custom_domain_on_sale"
#: Standard's card as 0013 and 0021 leave it: its description sold «your own domain» and its features «Custom domain
#: (erp.yourbusiness.com)». 0026 takes both off; the cards show that line from ``Plan.includes_custom_domain``.
CARD_0021 = {
    "description_en": "For growing businesses: your own domain, twice the resources and priority support.",
    "description_es": "Para negocios en crecimiento: dominio propio, el doble de recursos y soporte prioritario.",
    **COPY_0021["standard"],
}
CUSTOM_DOMAIN_CARD_COLUMNS = [("standard", column) for column in CARD_0021]


def _no_custom_domain():
    return import_module(f"hubs.migrations.{NO_CUSTOM_DOMAIN}")


def _forward_0026():
    _no_custom_domain().stop_selling_the_custom_domain(global_apps, _SchemaEditor())


def _backward_0026():
    _no_custom_domain().give_back_the_words_of_0021(global_apps, _SchemaEditor())


def _standard_card(Plan) -> dict:
    return _row(Plan.objects.get(slug="standard"), CARD_0021)


@pytest.mark.django_db
class TestNoCardSellsACustomDomainNobodyCanConnect:
    """Standard's card (the public web, its detail page and the Store) sold a custom domain in its own words; from
    0026 the card says only what the plan gives, and the custom-domain line comes from ``includes_custom_domain``, the
    gate HUBS-F17 reads. Each column moves only while it still reads 0021's words: what staff wrote in the admin is
    theirs."""

    @pytest.fixture
    def seeded_card(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug="standard").update(**CARD_0021)
        return Plan

    def test_the_old_card_sold_a_custom_domain_in_every_column_0026_writes(self):
        from hubs.tests.test_plan_catalogue import CUSTOM_DOMAIN_WORDS

        for column, words in CARD_0021.items():
            texts = words if isinstance(words, list) else [words]
            assert [text for text in texts if CUSTOM_DOMAIN_WORDS.search(text)], column

    def test_the_card_names_no_custom_domain_and_keeps_every_other_line(self, seeded_card):
        from hubs.tests.test_plan_catalogue import CUSTOM_DOMAIN_WORDS

        _forward_0026()

        card = _standard_card(seeded_card)
        assert card == COPY_0026["standard"]
        for column in ("features_en", "features_es"):
            assert [line for line in CARD_0021[column] if not CUSTOM_DOMAIN_WORDS.search(line)] == card[column], column
            assert len(card[column]) == len(CARD_0021[column]) - 1, column
        assert [text for text in [card["description_en"], card["description_es"]] if CUSTOM_DOMAIN_WORDS.search(text)] == []

    def test_the_custom_domain_gate_stays(self, seeded_card):
        _forward_0026()

        gates = dict(seeded_card.objects.values_list("slug", "includes_custom_domain"))
        assert {slug for slug, gate in gates.items() if gate} == {"standard", "pro", "enterprise", "max"}

    def test_nothing_but_those_columns_moves(self, seeded_card):
        before = _snapshot(seeded_card)

        _forward_0026()

        after = _snapshot(seeded_card)
        assert {slug: row for slug, row in after.items() if slug != "standard"} == {
            slug: row for slug, row in before.items() if slug != "standard"
        }
        assert after["standard"] == {**before["standard"], **COPY_0026["standard"]}

    @pytest.mark.parametrize(("slug", "column"), CUSTOM_DOMAIN_CARD_COLUMNS)
    def test_a_column_staff_rewrote_is_theirs(self, seeded_card, slug, column):
        edited = ["Edited by staff"] if column.startswith("features") else "Edited by staff"
        seeded_card.objects.filter(slug=slug).update(**{column: edited})

        _forward_0026()

        assert _standard_card(seeded_card) == {**COPY_0026["standard"], column: edited}

    def test_reversing_gives_back_the_words_of_0021(self, seeded_card):
        _forward_0026()
        _backward_0026()

        assert _standard_card(seeded_card) == CARD_0021

    @pytest.mark.parametrize(("slug", "column"), CUSTOM_DOMAIN_CARD_COLUMNS)
    def test_reversing_keeps_what_staff_wrote_after_it(self, seeded_card, slug, column):
        _forward_0026()
        edited = ["Edited by staff"] if column.startswith("features") else "Edited by staff"
        seeded_card.objects.filter(slug=slug).update(**{column: edited})

        _backward_0026()

        assert _standard_card(seeded_card) == {**CARD_0021, column: edited}

    def test_it_is_idempotent_and_survives_a_database_without_the_row(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug="standard").delete()
        for _ in range(2):
            _forward_0026()
            _backward_0026()

        assert not Plan.objects.filter(slug="standard").exists()

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        copy = _no_custom_domain().COPY

        assert [name for name in _imported_modules(_no_custom_domain()) if name.startswith("hubs")] == []
        assert {slug: {column: old for column, (old, _) in columns.items()} for slug, columns in copy.items()} == {
            "standard": CARD_0021
        }
        assert {slug: {column: new for column, (_, new) in columns.items()} for slug, columns in copy.items()} == COPY_0026


@pytest.mark.django_db
def test_hubs_migrates_back_before_0026_and_forward_again():
    """``migrate hubs 0025`` and back: Standard sells the custom domain again, then stops."""
    from hubs.models import Plan

    call_command("migrate", "hubs", "0025", verbosity=0)
    assert _standard_card(Plan) == CARD_0021

    call_command("migrate", "hubs", verbosity=0)
    assert _standard_card(Plan) == COPY_0026["standard"]


# --- 0029: the database line says what a recovery keeps --------------------------------------------

BACKUPS_KEEP = "0029_backups_keep_what_was_sent"
DATABASE_LINE_COLUMNS = [(slug, column) for slug in DATABASE_LINE_PLANS for column in LINES_0013]


def _backups_keep():
    return import_module(f"hubs.migrations.{BACKUPS_KEEP}")


def _forward_0029():
    _backups_keep().say_what_a_recovery_keeps(global_apps, _SchemaEditor())


def _backward_0029():
    _backups_keep().give_back_the_line_of_0013(global_apps, _SchemaEditor())


def _database_line_cards(Plan) -> dict[str, dict]:
    return {slug: _row(Plan.objects.get(slug=slug), LINES_0013) for slug in DATABASE_LINE_PLANS}


def _cards_of_0021() -> dict[str, dict]:
    return {slug: {column: COPY_0021[slug][column] for column in LINES_0013} for slug in DATABASE_LINE_PLANS}


@pytest.mark.django_db
class TestTheDatabaseLineSaysWhatARecoveryKeeps:
    """The cards of Free and Starter (the public web, the plan's page, the panel's Store and the assistant) promised a
    return to any moment of the last 14 days; a business that invoices with VeriFactu in production gets back what it
    lost from a copy of that moment, and what it sent to the tax agency stays. From 0029 the line says both. Only that
    line moves, wherever it still reads 0013's words: every other line, and a line staff rewrote, stay theirs."""

    @pytest.fixture
    def seeded_cards(self, plans):
        from hubs.models import Plan

        for slug, columns in _cards_of_0021().items():
            Plan.objects.filter(slug=slug).update(**columns)
        return Plan

    def test_the_old_line_promised_a_recovery_without_what_it_keeps_on_both_cards(self):
        for column, line in LINES_0013.items():
            assert promises_a_recovery_without_what_it_keeps(line), column
            for slug in DATABASE_LINE_PLANS:
                assert line in COPY_0021[slug][column], (slug, column)

    def test_the_line_says_what_a_recovery_keeps_in_its_place_and_nothing_else_moves(self, seeded_cards):
        _forward_0029()

        cards = _database_line_cards(seeded_cards)
        assert cards == COPY_0029
        for slug, columns in cards.items():
            for column, lines in columns.items():
                old = COPY_0021[slug][column]
                assert [(a, b) for a, b in zip(old, lines) if a != b] == [(LINES_0013[column], LINES_0029[column])]
                assert [line for line in lines if promises_a_recovery_without_what_it_keeps(line)] == [], (slug, column)

    def test_nothing_but_the_database_line_moves(self, seeded_cards):
        before = _snapshot(seeded_cards)

        _forward_0029()

        after = _snapshot(seeded_cards)
        assert {slug: row for slug, row in after.items() if slug not in DATABASE_LINE_PLANS} == {
            slug: row for slug, row in before.items() if slug not in DATABASE_LINE_PLANS
        }
        for slug in DATABASE_LINE_PLANS:
            assert after[slug] == {**before[slug], **COPY_0029[slug]}, slug

    @pytest.mark.parametrize(("slug", "column"), DATABASE_LINE_COLUMNS)
    def test_a_line_staff_rewrote_is_theirs(self, seeded_cards, slug, column):
        """Staff's words for the same line, which start as 0013's: only the exact line moves."""
        rewritten = f"{LINES_0013[column][:24]} — edited by staff"
        edited = [rewritten if line == LINES_0013[column] else line for line in COPY_0021[slug][column]]
        seeded_cards.objects.filter(slug=slug).update(**{column: edited})

        _forward_0029()

        assert _database_line_cards(seeded_cards)[slug][column] == edited

    @pytest.mark.parametrize(("slug", "column"), DATABASE_LINE_COLUMNS)
    def test_a_card_staff_edited_elsewhere_still_says_what_a_recovery_keeps(self, seeded_cards, slug, column):
        """The line is the unit, not the card: a line staff added does not keep the promise on sale."""
        seeded_cards.objects.filter(slug=slug).update(**{column: [*COPY_0021[slug][column], "Edited by staff"]})

        _forward_0029()

        assert _database_line_cards(seeded_cards)[slug][column] == [*COPY_0029[slug][column], "Edited by staff"]

    def test_reversing_gives_back_the_line_of_0013(self, seeded_cards):
        _forward_0029()
        _backward_0029()

        assert _database_line_cards(seeded_cards) == _cards_of_0021()

    @pytest.mark.parametrize(("slug", "column"), DATABASE_LINE_COLUMNS)
    def test_reversing_keeps_what_staff_wrote_after_it(self, seeded_cards, slug, column):
        _forward_0029()
        edited = ["Edited by staff" if line == LINES_0029[column] else line for line in COPY_0029[slug][column]]
        seeded_cards.objects.filter(slug=slug).update(**{column: edited})

        _backward_0029()

        assert _database_line_cards(seeded_cards)[slug][column] == edited

    def test_it_is_idempotent_and_survives_a_database_without_the_rows(self, seeded_cards):
        _forward_0029()
        _forward_0029()
        assert _database_line_cards(seeded_cards) == COPY_0029

        seeded_cards.objects.filter(slug__in=DATABASE_LINE_PLANS).delete()
        for _ in range(2):
            _forward_0029()
            _backward_0029()

        assert not seeded_cards.objects.filter(slug__in=DATABASE_LINE_PLANS).exists()

    def test_it_is_frozen_and_reads_nothing_of_the_code(self):
        lines = _backups_keep().LINES

        assert [name for name in _imported_modules(_backups_keep()) if name.startswith("hubs")] == []
        assert {column: old for column, (old, _) in lines.items()} == LINES_0013
        assert {column: new for column, (_, new) in lines.items()} == LINES_0029


@pytest.mark.django_db
def test_hubs_migrates_back_before_0029_and_forward_again():
    """``migrate hubs 0028`` and back: Free and Starter promise the window alone again, then say what it keeps."""
    from hubs.models import Plan

    call_command("migrate", "hubs", "0028", verbosity=0)
    assert _database_line_cards(Plan) == _cards_of_0021()

    call_command("migrate", "hubs", verbosity=0)
    assert _database_line_cards(Plan) == COPY_0029
