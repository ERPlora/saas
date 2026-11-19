"""The messages a month of each plan on ``/pricing/``, the AI assistant's and WhatsApp's: on the cards and in the
comparison table."""

from __future__ import annotations

import re

import pytest

from public.tests.pricing_pages import card_items, html_of, make_plan, plan_table, visible_markup

pytestmark = [pytest.mark.django_db]


# --- The monthly messages of each plan: assistant and WhatsApp ------------------------------------------


def test_each_card_says_the_assistant_and_whatsapp_messages_a_month(client, seeded):
    """In plain words, after the plan's features (and before a trial line, if staff give one): what the plan
    includes, never tokens nor how we count them."""
    html = html_of(client)

    assert card_items(html, "Free")[-2:] == ["AI assistant: 30 messages a month", "WhatsApp: 30 messages a month"]
    starter = card_items(html, "Starter")
    assert starter[-2:] == ["AI assistant: 300 messages a month", "WhatsApp: 150 messages a month"]
    assert not any("trial" in item for item in starter), starter
    assert "AI assistant: 600 messages a month" in card_items(html, "Standard")
    assert "WhatsApp: 300 messages a month" in card_items(html, "Standard")
    assert "token" not in visible_markup(html).lower()


def test_a_plan_without_messages_says_nothing_of_them(no_plans, client):
    """0 is «none»: the card paints no line rather than «0 messages»."""
    make_plan("starter", trial_days=15, assistant_messages_per_month=0, whatsapp_messages_per_month=40)

    assert card_items(html_of(client), "Starter") == [
        "Unlimited users", "All the apps turned on at once", "WhatsApp: 40 messages a month", "15-day free trial",
    ]  # fmt: skip


def test_one_message_reads_in_the_singular(no_plans, client):
    make_plan("starter", assistant_messages_per_month=1)

    assert "AI assistant: 1 message a month" in card_items(html_of(client), "Starter")


def test_the_cards_read_the_messages_in_spanish(client, seeded):
    items = card_items(html_of(client, language="es"), "Starter")

    assert "Asistente de IA: 300 mensajes al mes" in items
    assert "WhatsApp: 150 mensajes al mes" in items


def test_the_table_compares_the_messages_of_each_plan(client, seeded):
    table = plan_table(html_of(client))

    assert "<th>AI assistant</th>" in table and "<th>WhatsApp</th>" in table
    for messages in ("30 messages a month", "300 messages a month", "600 messages a month", "150 messages a month"):
        assert messages in table, messages
    # No row agrees its quota by contact.
    assert "Agreed with you" not in table


def test_a_plan_without_messages_reads_not_included_in_the_table(no_plans, client):
    make_plan("starter", assistant_messages_per_month=0, whatsapp_messages_per_month=0)

    assert plan_table(html_of(client)).count("Not included") == 2


def test_the_table_reads_the_messages_in_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert "<th>Asistente de IA</th>" in table
    assert "300 mensajes al mes" in table
    assert "Acordado contigo" not in table


def test_every_row_of_the_table_spans_its_columns(client, seeded):
    """A new column must reach the group rows too, or the table breaks on a wide screen."""
    table = plan_table(html_of(client))
    columns = len(re.findall(r"<th\b", table.split("</thead>", 1)[0]))

    assert set(re.findall(r'colspan="(\d+)"', table)) == {str(columns)}
