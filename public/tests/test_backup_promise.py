"""saas#1956: one cluster, one backup window, one sentence everywhere.

Port of ERPlora/saas ``apps/public/tests/test_backup_promise_is_consistent.py`` (origin/develop
c5ca8ca, 3). ``hubs/tests/test_sync_hub_plans.py`` pins the promise inside ``Plan.features``; this
sweeps the copy of the public templates (and their Spanish, which lives in the catalog), so the next
«daily backups» is caught wherever somebody writes it: Aurora backs up continuously, with
point-in-time recovery inside its retention window (aws-next), never «daily».

What changed: the old guard exempted ``landing/downloads.html``, frozen in ``pm/LOCKED.md``. Here the
exemptions are the four templates of the L3a port that say «daily backups» (reported to the
supervisor with this lot, L7: their copy and its Spanish belong to that lot, and the length of the
window is to be settled, 14 days in aws-next against the seed's «up to 30 days»). The list is
self-retiring, as the old one was: the day a template is fixed, ``test_the_exemptions_still_earn_their_place``
fails until it leaves the list.
"""

from pathlib import Path

import pytest
from django.conf import settings

PUBLIC_TEMPLATES = Path(settings.BASE_DIR) / "public" / "templates"
CATALOG = Path(settings.BASE_DIR) / "public" / "locale" / "es" / "LC_MESSAGES" / "django.po"
#: «Daily backup» in every shape the copy has used, in English and in Spanish.
DAILY_BACKUP_PATTERNS = (
    "daily backup",
    "copia diaria",
    "copias diarias",
    "backups diarios",
    "backup diario",
    "copias de seguridad diarias",
    "copia de seguridad diaria",
)
#: The templates (and their catalog entries) still to be fixed, see the module docstring.
PENDING = {
    "public/downloads.html": ("Managed PostgreSQL, daily backups",),
    "public/company/about.html": (
        "A cloud-native architecture on AWS, one database per hub, with daily backups",
    ),
    "public/product/_features_bento.html": ("Daily backups, TLS and high availability on AWS",),
    "public/product/_security_lists.html": ("High availability on AWS, with daily backups",),
}


def claims(text: str) -> list[str]:
    lowered = text.lower()
    return [pattern for pattern in DAILY_BACKUP_PATTERNS if pattern in lowered]


def template_offenders() -> dict[str, list[str]]:
    found = {}
    for path in sorted(PUBLIC_TEMPLATES.rglob("*.html")):
        if hits := claims(path.read_text(encoding="utf-8")):
            found[str(path.relative_to(PUBLIC_TEMPLATES))] = hits
    return found


def catalog_entries() -> list[tuple[str, str]]:
    """``(msgid, msgstr)`` of the public catalog, joined across their continuation lines."""
    entries, current, field = [], {"msgid": "", "msgstr": ""}, None
    for line in CATALOG.read_text(encoding="utf-8").splitlines() + [""]:
        if line.startswith(("msgid ", "msgstr ")):
            field, _, value = line.partition(" ")
            if field == "msgid" and current["msgstr"]:
                entries.append((current["msgid"], current["msgstr"]))
                current = {"msgid": "", "msgstr": ""}
            current[field] = value.strip('"')
        elif line.startswith('"') and field:
            current[field] += line.strip('"')
    entries.append((current["msgid"], current["msgstr"]))
    return entries


def test_no_public_template_promises_a_daily_backup():
    unexpected = {path: hits for path, hits in template_offenders().items() if path not in PENDING}

    assert unexpected == {}, (
        "Aurora backs up continuously, with point-in-time recovery (aws-next): never «daily»"
    )


def test_no_spanish_message_promises_a_daily_backup():
    pending = [msgid for msgids in PENDING.values() for msgid in msgids]
    offenders = [
        msgid
        for msgid, msgstr in catalog_entries()
        if claims(msgstr) and not any(sentence in msgid for sentence in pending)
    ]

    assert offenders == []


def test_the_exemptions_still_earn_their_place():
    """Self-retiring: an exemption whose template no longer makes the claim must leave the list."""
    assert set(PENDING) - set(template_offenders()) == set()


@pytest.mark.parametrize(
    "sentence",
    [
        "Managed PostgreSQL, daily backups",
        "Copias diarias incluidas",
        "backup diario cifrado",
        "con copias de seguridad diarias",
    ],
)
def test_the_patterns_catch_the_sentences_that_were_actually_written(sentence):
    """Positive control: a sweep nobody has seen fail is a sweep nobody can trust."""
    assert claims(f"<span>{sentence}</span>")
