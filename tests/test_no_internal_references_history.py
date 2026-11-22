"""Where a piece was copied from in the old product, that product's decisions and flows, and the day something
happened: the history keeps them, so they are caught in prose, and left alone in data."""

import pytest
from test_no_internal_references import (
    DATED_NOTE,
    OLD_PRODUCT_APPS,
    OLD_PRODUCT_RECORD,
    OLD_PRODUCT_SOURCE,
    REPO,
    internal_references,
)


@pytest.mark.parametrize(
    "text",
    [
        "Ported from ERPlora/saas ``apps/dashboard/fiscal/nif.py`` (origin/develop).",
        "Port of ``apps/public/downloads.py`` (origin/develop c5ca8ca). The hub's CI",
        "``config/context_processors.py``, origin/develop c5ca8ca; only the public part",
        "ported from ../erplora/views.py @ abc1234",
        "taken from the Hub's catalog (hub origin/main@b128e6e8)",
        "took the whole site down in CI (hotfix cfc4adb)",
        "``SocialAccountAdapter`` is ported from ERPlora/saas ``ERPloraSocialAccountAdapter``",
        "the frame of every account screen, ported from ERPlora/saas's partials",
        "Ported from the old ``WhatsAppPhoneMapping`` (``../ERPlora/saas`` ``models.py``)",
        "ACCOUNTS-F17 (old ``fi:saas/auth-services#revocar-dispositivo-de-confianza``)",
        "the old guard exempted ``landing/downloads.html``, frozen in ``pm/LOCKED.md``",
        "It carries no VAT figure on purpose (WORKFLOW F55)",
        "(``apps/auth/users/adapters.py``)",
        "``apps/core/emails.py`` (``brand_context``)",
    ],
)
def test_the_scan_catches_where_a_piece_came_from_in_the_old_product(text):
    assert OLD_PRODUCT_SOURCE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "its read-only admin and its checks (``apps/tests/test_lint.py``)",
        "cleaned with nh3 by the SaaS, `apps/icons.py`",
        "the operations of the Store: billing/api.py, apps/api.py and hubs/api.py",
        "How long the Hub reads the gateway (``hub`` ``apps/verifactu/gateway.py``)",
        "the Hub calls them from ``apps/whatsapp_inbox/gateway.py``",
        "the OIDC subject (repo:ERPlora/saas:ref:refs/heads/<branch>)",
        "a request is answered for its real path (ERPlora/saas#89)",
        "https://github.com/ERPlora/saas/pull/12",
        "`#fff` at 15% → `#ffffff26`",
        "digits off a hex token (``612345678a…``) and leave the rest in clear",
        "the usage of the demo ``demo-0e2ea55e``",
        "in ``+34612345678`` there is no word boundary",
        "a branch off main, merged when green",
        "the mail goes out as noreply@erplora.com",
        "the develop server answers on port 8001",
    ],
)
def test_the_scan_leaves_this_repositorys_paths_and_other_hex_alone(text):
    assert not OLD_PRODUCT_SOURCE.search(text)


def test_the_old_products_app_folders_are_none_of_this_repositorys():
    assert not [name for name in OLD_PRODUCT_APPS if (REPO / "apps" / name).exists()]


@pytest.mark.parametrize(
    "text",
    [
        "Sign-up is open, as in today's SaaS (ADR-0154)",
        "of the installable app (ADR-0196/0160/0180)",
        "the turn passes through and is forgotten (ADR-0149 of the old product)",
        "with a Google that vouches for the account's own address (SAAS_AUTH-F04)",
        "(old SAAS_ASSISTANT-F22 step 2 and 4)",
        "which kept no record of it (old-saas:SAAS_PUBLIC-F72)",
        "counted by the address (SAAS-F05)",
    ],
)
def test_the_scan_catches_the_old_products_decisions_and_flows(text):
    assert OLD_PRODUCT_RECORD.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "Trust this browser for 14 days (ACCOUNTS-F05)",
        "the Hub's BASE-F114 gives back what it lost",
        "for the Hub's WHATSAPP_INBOX-F27 (Meta's verdict and reason)",
        "an automation's step (FLOW-F38)",
        "the ADRs of the platform",
        "the SAAS-wide setting",
    ],
)
def test_the_scan_leaves_this_repositorys_and_the_hubs_flows_alone(text):
    assert not OLD_PRODUCT_RECORD.search(text)


def test_this_repositorys_flows_are_not_named_as_the_old_products():
    headings = [
        line
        for workbook in REPO.glob("*/WORKBOOK*.md")
        for line in workbook.read_text(encoding="utf-8").splitlines()
        if line.startswith("### ")
    ]
    assert headings, "no WORKBOOK flow was read"
    assert not [heading for heading in headings if OLD_PRODUCT_RECORD.search(heading)]


@pytest.mark.parametrize(
    "text",
    [
        "symbol that was not on main took the whole site down in CI (2026-10-14, the hotfix).",
        "kept in the admin (2026-10-15).",
        "The modules a business may choose to turn on (2026-10-24; what they require does not count)",
        "the public repo ``ERPlora/app`` (Linux, 2026-10-27)",
        "the default since 2026-10-23",
        "until 2026-10-28 the panel asked twice",
        "as of 2026-11-01 the listing is live",
        "before 2026-10-15 the seed carried it",
        " # 2026-11-03), so it is named as what it is",
        "   2026-06-11). Same pattern as the assistant's drawer",
    ],
)
def test_the_scan_catches_a_dated_note(text):
    assert DATED_NOTE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "# Generated by Django 6.1.2 on 2026-10-13 11:20",
        "What the Hub measured yesterday (the clock is 2026-10-14 below).",
        'the rows of each day (``"2026-10-13"`` → ``[{id, s3_bytes, …}]``)',
        "the entry's page printed it raw («2026-10-23 11:46:10.268295+02:00»)",
        "the API version the SDK pins (2026-09-30: the period on the subscription items)",
        "``seal B27593136, expires 2027-10-15``: what it is",
        "Since ``2025-03-31.basil`` the period lives on ``items.data[]``",
        "The tax data of 2026-10-14: the EU-27 general rates",
        "a timestamp in UTC (2026-10-13T11:20:00Z)",
        "the period (2026-10-01 → 2026-10-31) of the invoice",
    ],
)
def test_the_scan_leaves_a_date_as_data_alone(text):
    assert not DATED_NOTE.search(text)


def test_the_old_product_and_a_dated_note_are_caught_in_prose_but_not_in_data(tmp_path):
    (tmp_path / "public").mkdir()
    lines = (
        '"""Port of ``apps/public/downloads.py`` (origin/develop c5ca8ca)."""',
        'SOURCE = "origin/develop"',
        "# Sign-up is open (ADR-0154).",
        'FLOW = "SAAS_AUTH-F04"',
        "# The default since 2026-10-23.",
        'DAY = "(2026-10-23)"',
        "# The rows of each day (``2026-10-13`` → its figures).",
        "# The Hub's own icons (``apps/icons.py``).",
    )
    (tmp_path / "public" / "downloads.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "public" / "page.html").write_text(
        "{# Port of apps/public/pricing/templates/pricing/index.html (origin/develop) #}\n"
        '<p data-flow="SAAS_AUTH-F04">2026-10-23</p>\n',
        encoding="utf-8",
    )
    (tmp_path / "public" / "Card.vue").write_text(
        '<script setup lang="ts">\n'
        "// Ported from ERPlora/saas's `account/_auth_header.html`.\n"
        "const since = '(2026-10-14)';\n"
        "it('keeps the browser trusted (old SAAS_AUTH-F06)', () => {});\n",
        encoding="utf-8",
    )
    found = internal_references(["public/downloads.py", "public/page.html", "public/Card.vue"], root=tmp_path)
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "public/downloads.py:1",
        "public/downloads.py:3",
        "public/downloads.py:5",
        "public/page.html:1",
        "public/Card.vue:2",
        "public/Card.vue:4",
    ]
