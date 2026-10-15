"""saas#1956: one cluster, one backup window, one sentence everywhere.

Port of ERPlora/saas ``apps/public/tests/test_backup_promise_is_consistent.py`` (origin/develop
c5ca8ca, 3). ``hubs/tests/test_plan_catalogue.py`` pins the promise inside ``Plan.features``; this
sweeps the copy of the public templates (and their Spanish, which lives in the catalog), so the next
«daily backups» is caught wherever somebody writes it: Aurora backs up continuously, with
point-in-time recovery inside its retention window (aws-next), never «daily».

What changed: the old guard exempted ``landing/downloads.html``, frozen in ``pm/LOCKED.md``. The four
templates of the L3a port that said «daily backups» now say what aws-next does (Aurora,
``backup_retention_period = 14``, continuous with point-in-time recovery), in the same words as the
plans of the panel (``hubs/migrations/0013_plans_in_the_database.py``), so ``PENDING`` is empty. The list
stays self-retiring, as the old one was: an exemption whose template no longer makes the claim makes
``test_the_exemptions_still_earn_their_place`` fail until it leaves the list.
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
PENDING: dict[str, tuple[str, ...]] = {}
#: The promise, as the plans of the panel word it (hubs/migrations/0013_plans_in_the_database.py).
PROMISE = {
    "en": "point-in-time recovery for 14 days",
    "es": "recuperación a cualquier momento de los últimos 14 días",
}
#: The pages that state it: the ways to try ERPlora, about, features and security.
PAGES_WITH_THE_PROMISE = ("/download/", "/about/", "/features/", "/security/")


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


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", PAGES_WITH_THE_PROMISE)
def test_the_pages_promise_what_aurora_does(client, path, language):
    """aws-next: Aurora backs up continuously, ``backup_retention_period = 14``."""
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)

    assert response.status_code == 200
    assert PROMISE[language] in response.content.decode()
