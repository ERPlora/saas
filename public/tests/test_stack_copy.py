"""The public web says what ERPlora does, never what it is built with (Ioan, 2026-10-14).

«We don't need to say which technology we use»: ``/features/`` loses its «Built with modern
technology.» section (the stack cards: Ionic, Vue, Django, PostgreSQL) and its «Cloud-native» cell,
``/about/`` its «Built with Django 6.1 and modern web components…», ``/download/`` its «Managed
PostgreSQL» and the cookie policy the «(Django)» of its two technical cookies. This sweeps the copy
of the public templates (template comments and scripts aside: they are for developers), their
Spanish in the catalog and the help guides, so the next «Built on Django» is caught wherever
somebody writes it.

The guarantees a buyer asks about are not the stack: ``/security/`` keeps TLS, PBKDF2 and AWS, and
it is not touched here. Its «Cookie consent (django-cookie-consent)» is the one exemption, and it
retires itself as in ``test_backup_promise.py``: once the page no longer says it, the exemption has
to leave the list.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

from public.tests.test_backup_promise import catalog_entries

ROOT = Path(settings.BASE_DIR)
PUBLIC_TEMPLATES = ROOT / "public" / "templates"
HELP_GUIDES = sorted((ROOT / "docs").glob("*/help/*.md"))

#: The names of the stack, as the copy used them. Whole words only: «vuelve» or «invites» are not.
STACK = re.compile(
    r"\b(?:django|ionic|vue|postgres(?:ql)?|vite|python|tauri|cloud[- ]?native|web components)\b",
    re.IGNORECASE,
)
#: What a developer reads and a visitor never does.
TEMPLATE_COMMENT = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|\{#.*?#\}", re.S
)
SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.IGNORECASE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
#: ``(template, sentence)`` still allowed to name a piece of the stack, see the module docstring.
EXEMPT: tuple[tuple[str, str], ...] = (
    ("public/product/_security_lists.html", "Cookie consent (django-cookie-consent)"),
)


def names_the_stack(text: str) -> list[str]:
    """The names of the stack in a piece of copy (a template, a rendered page, a message)."""
    return STACK.findall(text)


def copy_of(source: str) -> str:
    """What a template or a rendered page shows a visitor or a crawler: no template comment, no
    script, no HTML comment."""
    return HTML_COMMENT.sub("", SCRIPT.sub("", TEMPLATE_COMMENT.sub("", source)))


def template_offenders() -> dict[str, list[str]]:
    found = {}
    for path in sorted(PUBLIC_TEMPLATES.rglob("*.html")):
        name = str(path.relative_to(PUBLIC_TEMPLATES))
        source = copy_of(path.read_text(encoding="utf-8"))
        for template, sentence in EXEMPT:
            if template == name:
                source = source.replace(sentence, "")
        if hits := names_the_stack(source):
            found[name] = hits
    return found


def test_no_public_template_names_the_stack():
    assert template_offenders() == {}, (
        "say what ERPlora does, not what it is built with"
    )


def test_no_message_of_the_public_catalog_names_the_stack():
    exempt = {sentence for _, sentence in EXEMPT}
    offenders = [
        (msgid, msgstr)
        for msgid, msgstr in catalog_entries()
        if msgid and msgid not in exempt and names_the_stack(f"{msgid} {msgstr}")
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "guide", HELP_GUIDES, ids=lambda path: f"{path.parts[-3]}/{path.name}"
)
def test_no_help_guide_names_the_stack(guide):
    assert names_the_stack(guide.read_text(encoding="utf-8")) == []


def test_the_exemptions_still_earn_their_place():
    """Self-retiring: an exemption whose template no longer says it must leave the list."""
    for template, sentence in EXEMPT:
        assert sentence in copy_of(
            (PUBLIC_TEMPLATES / template).read_text(encoding="utf-8")
        ), template


@pytest.mark.parametrize(
    "sentence",
    [
        "Built on Django 6.1, with live updates on every device.",
        "✓ Ionic (Web Components)",
        "✓ Vue 3 (Reactivity & Interactivity)",
        "✓ PostgreSQL 18",
        "Built with Django 6.1 and modern web components.",
        "A cloud-native architecture on AWS",
        "Managed PostgreSQL, with continuous backups",
        "(Django): keeps you logged in.",
        "Diseño cloud-native",
    ],
)
def test_the_sweep_catches_the_sentences_that_were_actually_written(sentence):
    """Positive control: a sweep nobody has seen fail is a sweep nobody can trust."""
    assert names_the_stack(f"<span>{sentence}</span>")


@pytest.mark.parametrize(
    "sentence",
    [
        "Vuelve a iniciar sesión",
        "Invites your team",
        "Your hub, in the cloud",
        "{# Django #}",
    ],
)
def test_the_sweep_leaves_alone_what_is_not_the_stack(sentence):
    """Negative control: Spanish «vuelve», «invites» and a template comment are not the stack."""
    assert names_the_stack(copy_of(sentence)) == []
