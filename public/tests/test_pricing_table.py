"""The comparison table of ``/pricing/``: the devices, users, resources and support each plan buys, in plain
words."""

from __future__ import annotations

import re

import pytest

from public import pricing
from public.tests.pricing_pages import COLUMNS, html_of, plan_table

pytestmark = [pytest.mark.django_db]


# --- The comparison table ---------------------------------------------------------------------


def test_table_shows_the_devices_and_users_each_plan_buys(client, seeded):
    table = plan_table(html_of(client))

    assert "1 device" in table
    assert "3 users" in table
    assert "Unlimited devices" in table
    assert "Unlimited users" in table


def test_table_shows_the_support_of_each_plan(client, seeded):
    """The plans on sale, then the upgrade-only ones; no dedicated row."""
    table = plan_table(html_of(client))
    signable, upgrades = table.split(f'<td colspan="{COLUMNS}">More capacity</td>', 1)

    for support in ("Community forum", "Email", "Priority email"):
        assert support in signable, support
    for gone in ("Pro", "Enterprise", "Agreed in contract"):
        assert gone not in signable, gone
    for shown in ("<strong>Pro</strong>", "<strong>Enterprise</strong>", "Priority email", "Agreed in contract"):
        assert shown in upgrades, shown
    assert "Dedicated, agreed with you" not in table


def test_table_shows_the_resources_each_plan_buys_in_plain_words(client, seeded):
    """The «resources» that grow from plan to plan are the database's input/output capacity.
    Free for one device, Starter the full tier, Standard twice it — a buyer reads the ladder as database
    throughput, never an engine, a connection count nor a timeout."""
    table = plan_table(html_of(client))

    assert "Database throughput" in table
    for label in ("Basic, for one device", "Full, for several devices", "Double"):
        assert label in table, label
    assert "Your own, sized with you" not in table
    assert not re.search(r"\b(connections?|timeout|aurora)\b", table, re.I)


def test_the_table_reads_the_resources_in_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert "Capacidad de la base de datos" in table
    for label in ("Básica, para un dispositivo", "Completa, para varios dispositivos", "El doble"):
        assert label in table, label
    assert "Propia, a tu medida" not in table


def test_the_limits_answer_says_each_plan_up_doubles_the_resources(client):
    (item,) = [item for item in pricing.faq_items() if item["key"] == "limits"]

    assert "doubles" in str(item["answer"])


def test_table_does_not_compare_plans_on_the_database_engine(client, seeded):
    assert "PostgreSQL" not in plan_table(html_of(client))


def test_the_engine_guard_reads_the_table_and_not_the_whole_page(client, seeded):
    """Positive control: the cards outside the table DO carry the database line."""
    html = html_of(client)

    assert "Managed database" in html
    assert "Managed database" not in plan_table(html)


def test_support_column_states_channel_and_priority_but_never_a_clock(client, seeded):
    table = plan_table(html_of(client))

    assert "24/7" not in table
    assert "business hours" not in table.lower()


def test_the_columns_survive_translation_to_spanish(client, seeded):
    table = plan_table(html_of(client, language="es"))

    assert "Dispositivos y usuarios" in table
    assert "Apps incluidas" not in table
    assert "1 dispositivo" in table
    assert "3 usuarios" in table
    assert "Dispositivos ilimitados" in table
    assert "Foro de la comunidad" in table
    assert "Correo electrónico prioritario" in table
