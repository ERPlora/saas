"""ASSISTANT-F27 · What the panel's assistant knows of ERPlora (``assistant.knowledge``): the documentation cut into
the excerpts its search returns (plan 2026-10-30-asistente-saas §5).

``chunk_markdown`` cuts a document at its ``##`` and ``###`` headings (a FAQ's questions are ``###``), names each
excerpt by its path of headings («Title > Section > Question») and windows a long section into excerpts of
``MAX_WORDS`` words that overlap by ``OVERLAP_WORDS``, so a sentence cut at the edge of one is whole in the next. The
four sources: the public help (``docs/<lang>/help/*.md``, never a guide still waiting for its translation), the user
documentation of the Hub's apps (``apps.doc.list``), the customer's part of the WORKBOOKs of the panel's apps (never
what is written for the maintainers) and one document of the plans on sale per language, from the database, so the
assistant never quotes a price from memory.
"""

from decimal import Decimal

import pytest

from apps.tests.factories import make_app, make_doc
from assistant import knowledge
from assistant.knowledge import Chunk, Section, chunk_markdown

GUIDE = """# Getting started

Sign in with the email of your account.

## The first time

Open erplora.com and choose Sign in.

## Signing in again

Type your PIN.
"""

FAQ = """# FAQ

## Access

### Why do I see a password instead of the PIN pad?

Because this device has never signed in.

### Is there a set-up wizard?

No: every app is set up on its own screen.
"""


def words(count: int, start: int = 0) -> str:
    return " ".join(f"w{index}" for index in range(start, start + count))


class TestChunkMarkdown:
    def test_each_section_is_an_excerpt_named_by_the_title_and_its_heading(self):
        assert chunk_markdown(GUIDE) == [
            Section("Getting started", "Sign in with the email of your account."),
            Section("Getting started > The first time", "Open erplora.com and choose Sign in."),
            Section("Getting started > Signing in again", "Type your PIN."),
        ]

    def test_a_question_under_a_section_is_named_by_both(self):
        assert chunk_markdown(FAQ) == [
            Section("FAQ > Access > Why do I see a password instead of the PIN pad?", "Because this device has never signed in."),
            Section("FAQ > Access > Is there a set-up wizard?", "No: every app is set up on its own screen."),
        ]

    def test_a_given_title_names_a_document_without_its_own(self):
        assert chunk_markdown("## Prices\n\nNet, VAT excluded.\n", title="Plans") == [
            Section("Plans > Prices", "Net, VAT excluded.")
        ]

    def test_a_long_section_is_windowed_with_an_overlap(self):
        pieces = chunk_markdown(f"## Long\n\n{words(500)}\n")

        assert [piece.text for piece in pieces] == [words(220), words(220, 170), words(160, 340)]
        assert {piece.heading for piece in pieces} == {"Long"}

    def test_a_section_of_exactly_the_window_is_one_excerpt(self):
        assert [piece.text for piece in chunk_markdown(f"## Fits\n\n{words(220)}\n")] == [words(220)]

    def test_comments_and_headings_inside_code_are_not_cut(self):
        text = "# Doc\n\n## Real\n\nBefore.\n<!-- origen: old-saas -->\n```\n## not a heading\n```\nAfter.\n"

        [piece] = chunk_markdown(text)

        assert piece.heading == "Doc > Real"
        assert "origen" not in piece.text
        assert "## not a heading" in piece.text and piece.text.endswith("After.")

    def test_a_comment_over_several_lines_goes_whole(self):
        [piece] = chunk_markdown("## Section\n\nKept.\n<!--\nhidden\n-->\nAlso kept.\n")

        assert piece.text == "Kept. Also kept."

    def test_an_empty_document_has_no_excerpt(self):
        assert chunk_markdown("# Only a title\n\n<!-- nothing -->\n") == []


class TestChunk:
    def test_the_hash_changes_with_any_of_what_it_says_and_where(self):
        base = Chunk("help", "docs/en/help/01.md", "en", "Guide", "Text.")
        others = [
            Chunk("help", "docs/en/help/01.md", "en", "Guide", "Other text."),
            Chunk("help", "docs/en/help/01.md", "en", "Other guide", "Text."),
            Chunk("help", "docs/en/help/01.md", "es", "Guide", "Text."),
            Chunk("help", "docs/en/help/02.md", "en", "Guide", "Text."),
            Chunk("workbook", "docs/en/help/01.md", "en", "Guide", "Text."),
        ]

        assert len(base.content_hash) == 64
        assert base.content_hash == Chunk("help", "docs/en/help/01.md", "en", "Guide", "Text.").content_hash
        assert base.content_hash not in {other.content_hash for other in others}

    def test_what_is_embedded_carries_its_headings(self):
        assert Chunk("help", "p", "en", "FAQ > Access", "Because.").embedding_text == "FAQ > Access\nBecause."


# --- The sources -----------------------------------------------------------------------------------------------


def write(root, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestTheHelp:
    def test_every_guide_of_each_language_with_its_path(self, tmp_path):
        write(tmp_path, "docs/en/help/01-getting-started.md", GUIDE)
        write(tmp_path, "docs/es/help/05-faq.md", "# Preguntas frecuentes\n\n## Acceso\n\n### ¿Por qué?\n\nPorque sí.\n")

        chunks = knowledge.help_chunks(tmp_path)

        assert {(chunk.path, chunk.lang) for chunk in chunks} == {
            ("docs/en/help/01-getting-started.md", "en"),
            ("docs/es/help/05-faq.md", "es"),
        }
        assert {chunk.source for chunk in chunks} == {"help"}
        assert Chunk("help", "docs/es/help/05-faq.md", "es", "Preguntas frecuentes > Acceso > ¿Por qué?", "Porque sí.") in chunks
        assert len([chunk for chunk in chunks if chunk.lang == "en"]) == 3

    def test_a_guide_waiting_for_its_translation_is_skipped(self, tmp_path):
        write(tmp_path, "docs/en/help/04-settings.md", GUIDE)
        write(tmp_path, "docs/es/help/04-settings.md", "<!-- pending translation from en -->\n")

        assert {chunk.lang for chunk in knowledge.help_chunks(tmp_path)} == {"en"}

    def test_the_help_this_project_ships_is_indexed_in_both_languages(self, settings):
        from pathlib import Path

        chunks = knowledge.help_chunks(Path(settings.BASE_DIR))

        assert {chunk.lang for chunk in chunks} == {"en", "es"}
        assert {chunk.path for chunk in chunks} >= {"docs/en/help/05-faq.md", "docs/es/help/05-faq.md"}


@pytest.mark.django_db
class TestTheAppsDocumentation:
    def test_each_listed_app_in_each_language_named_by_the_app(self):
        appointments = make_app("appointments", name_en="Appointments", name_es="Citas")
        make_doc(appointments, "es", "## Pedir cita\n\nElige el día.\n")
        make_doc(appointments, "en", "## Book\n\nChoose the day.\n")
        make_doc(make_app("retired", listed=False), "es", "## Old\n\nGone.\n")
        make_doc(make_app("blank"), "en", "")

        chunks = knowledge.collect("app_doc")

        assert sorted(chunks, key=lambda chunk: chunk.lang) == [
            Chunk("app_doc", "app_doc:appointments", "en", "Appointments > Book", "Choose the day."),
            Chunk("app_doc", "app_doc:appointments", "es", "Citas > Pedir cita", "Elige el día."),
        ]


HUBS_WORKBOOK = """# Workbook — Negocios (hubs)
Prefijo: HUBS
Estado de la app: en uso

> Manual de uso.

## Para qué sirve

Crear y abrir negocios.
<!-- origen: nuevo -->

## Flujos

### HUBS-F01 Crear un negocio
Pasos:
1. Pulsa «Crear negocio».

## Para quien lo mantiene

- `hubs/services.py` crea el negocio.
"""

HUBS_WORKBOOK_EN = """<!-- generated from WORKBOOK.md sha256:0000 -->

## What it is for

Create and open businesses.

## Flows

### HUBS-F01 Create a business
Steps:
1. Press «Create business».
"""


class TestTheWorkbooks:
    def test_only_the_customers_part_of_each_language(self, tmp_path):
        write(tmp_path, "hubs/WORKBOOK.md", HUBS_WORKBOOK)
        write(tmp_path, "hubs/WORKBOOK.en.md", HUBS_WORKBOOK_EN)

        chunks = knowledge.workbook_chunks(tmp_path)
        spanish = [chunk for chunk in chunks if chunk.lang == "es"]
        english = [chunk for chunk in chunks if chunk.lang == "en"]

        assert [(chunk.heading, chunk.text) for chunk in spanish] == [
            ("Negocios > Para qué sirve", "Crear y abrir negocios."),
            ("Negocios > Flujos > HUBS-F01 Crear un negocio", "Pasos: 1. Pulsa «Crear negocio»."),
        ]
        assert [(chunk.heading, chunk.text) for chunk in english] == [
            ("Businesses > What it is for", "Create and open businesses."),
            ("Businesses > Flows > HUBS-F01 Create a business", "Steps: 1. Press «Create business»."),
        ]
        assert {chunk.path for chunk in spanish} == {"hubs/WORKBOOK.md"}
        assert {chunk.path for chunk in english} == {"hubs/WORKBOOK.en.md"}
        assert {chunk.source for chunk in chunks} == {"workbook"}
        everything = " ".join(chunk.text for chunk in chunks)
        assert "services.py" not in everything and "Prefijo" not in everything and "sha256" not in everything

    def test_the_workbooks_of_the_panel_apps_and_not_the_staffs(self, tmp_path):
        for app in (*knowledge.WORKBOOK_APPS, "assistant", "fiscal"):
            write(tmp_path, f"{app}/WORKBOOK.md", HUBS_WORKBOOK)

        indexed = {chunk.path.split("/")[0] for chunk in knowledge.workbook_chunks(tmp_path)}

        assert indexed == {"accounts", "hubs", "billing", "apps", "public"}

    def test_a_workbook_without_the_maintainers_heading_is_refused(self, tmp_path):
        write(tmp_path, "hubs/WORKBOOK.md", "# Workbook\n\n## Para qué sirve\n\nTodo.\n")

        with pytest.raises(knowledge.WorkbookWithoutCut, match="hubs/WORKBOOK.md"):
            knowledge.workbook_chunks(tmp_path)

    def test_the_workbooks_this_project_ships_are_indexed_in_both_languages(self, settings):
        from pathlib import Path

        chunks = knowledge.workbook_chunks(Path(settings.BASE_DIR))

        assert {(chunk.path, chunk.lang) for chunk in chunks} >= {
            (f"{app}/WORKBOOK{suffix}", lang)
            for app in knowledge.WORKBOOK_APPS
            for suffix, lang in ((".md", "es"), (".en.md", "en"))
        }
        assert not [chunk for chunk in chunks if "Para quien lo mantiene" in chunk.heading]


@pytest.mark.django_db
class TestThePlans:
    def test_one_document_per_language_with_every_plan_on_sale_and_its_price(self, plans):
        from hubs.models import Plan

        chunks = knowledge.collect("plans")

        assert {chunk.lang for chunk in chunks} == {"en", "es"}
        assert {chunk.path for chunk in chunks} == {"plans"} and {chunk.source for chunk in chunks} == {"plans"}
        for lang, price in (("en", "{:.2f}"), ("es", "{:.2f}")):
            text = " ".join(f"{chunk.heading} {chunk.text}" for chunk in chunks if chunk.lang == lang)
            for plan in Plan.objects.public():
                assert plan.translated("name", lang) in text
                assert price.format(plan.price_monthly).replace(".", "," if lang == "es" else ".") in text

    def test_each_plan_says_what_it_includes(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug="starter").update(
            price_monthly=Decimal("19.90"), max_devices=3, max_apps=12, assistant_messages_per_month=300
        )

        [starter] = [chunk for chunk in knowledge.collect("plans") if chunk.lang == "en" and "Starter" in chunk.heading]

        assert "19.90 € a month" in starter.text
        assert "Up to 3 devices." in starter.text and "Up to 12 apps turned on at once" in starter.text
        assert "300 messages a month with the assistant." in starter.text
        assert "VAT excluded" in starter.text

    def test_in_spanish_too(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug="starter").update(price_monthly=Decimal("19.90"), max_devices=3)

        [starter] = [chunk for chunk in knowledge.collect("plans") if chunk.lang == "es" and "Starter" in chunk.heading]

        assert "19,90 € al mes" in starter.text and "Hasta 3 dispositivos." in starter.text and "IVA no incluido" in starter.text

    def test_no_limit_is_said_so(self, plans):
        from hubs.models import Plan

        Plan.objects.filter(slug="starter").update(max_devices=0, max_apps=0, max_users=0)

        [starter] = [chunk for chunk in knowledge.collect("plans") if chunk.lang == "en" and "Starter" in chunk.heading]

        assert "Unlimited users." in starter.text and "Unlimited devices." in starter.text
        assert "No limit on the apps turned on." in starter.text


def test_collect_knows_the_four_sources():
    assert knowledge.SOURCES == ("help", "app_doc", "workbook", "plans")
    with pytest.raises(ValueError):
        knowledge.collect("code")
