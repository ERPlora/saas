"""The legal pages of the public web: ``/legal/privacy/``, ``/legal/cookies/``,
``/legal/legal-notice/`` and ``/legal/terms/`` (spec §8.1; the terms read ``Plan`` and came with L7,
whose cases are at the end of this file).

Ported from ERPlora/saas (origin/develop c5ca8ca): ``apps/public/legal/tests/test_cookies_es.py``
(2), ``test_legal_notice.py`` (2) and ``test_privacy_es.py`` (10); the legal cases of
``tests/unit/test_public_pages.py`` (the page loads, mentions privacy, resolves, and the footer links
it); and the legal half of ``apps/public/landing/tests/test_ui_stack_contract.py`` (the shared
reading pattern), with the ``ep-*`` classes that replace OutfitKit's ``ok-*`` (PLAN §16.11). The
declaración responsable has its own file, ``test_declaracion.py``.

New here: the cookie policy names the cookies this site really sets (the old page named a
``django_language`` cookie nobody set: the language cookie is ``_lang``), the footer, the sitemap and
``llms.txt`` link the pages, no internal link of a legal page is dead (the Terms of Use are only
linked once their page exists), every message of the legal templates has its Spanish entry in
``public``'s compiled catalog (UI in ``en`` + ``es``, plan §3.j), and the privacy policy names AWS
as the host instead of Hetzner (Ioan, 2026-10-13), in its Ireland region, eu-west-1, the one of SES
too (Ioan, 2026-10-14: the ERP serves all of Europe, not the Spain region it named before).
"""

import ast
import gettext
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from django.utils.translation.template import templatize

from public.sitemaps import StaticPagesSitemap

ROOT = Path(settings.BASE_DIR)
LEGAL_TEMPLATES = ROOT / "public" / "templates" / "public" / "legal"
CATALOG = ROOT / "public" / "locale" / "es" / "LC_MESSAGES" / "django.mo"
HOST = "localhost:8001"

PAGES = {
    "public:privacy": "/legal/privacy/",
    "public:cookies": "/legal/cookies/",
    "public:legal_notice": "/legal/legal-notice/",
    # L7: it reads Plan (the trial of §4).
    "public:terms": "/legal/terms/",
}


def spanish(client, path: str) -> str:
    # English is the source language (real i18n via {% trans %}), so the Spanish page has to be
    # asked for with the language cookie.
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "es"
    return client.get(path).content.decode()


# --- Routes ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "path"), PAGES.items())
def test_the_legal_routes(name, path):
    assert reverse(name) == path
    assert resolve(path).view_name == name


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
def test_each_legal_page_is_public(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
def test_a_legal_page_only_answers_safe_methods(client, path):
    assert client.post(path).status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
def test_no_internal_link_of_a_legal_page_is_dead(client, path):
    """A link from a legal page to a 404 is a broken promise (the Terms of Use, named on the
    privacy page, were linked only once ``/legal/terms/`` existed, L7)."""
    html = client.get(path).content.decode()
    links = {
        href
        for href in re.findall(r'href="(/[^"]*)"', html)
        if not href.startswith("/static/")
    }

    for href in sorted(links):
        # follow: an old address may answer a redirect to its page.
        assert client.get(href, follow=True).status_code == 200, f"{path} links {href}"


# --- Cookie policy (test_cookies_es.py) --------------------------------------------------------


@pytest.mark.django_db
def test_cookies_returns_200(client):
    assert client.get("/legal/cookies/").status_code == 200


@pytest.mark.django_db
def test_cookies_contains_spanish_marker(client):
    assert "Política de cookies" in spanish(client, "/legal/cookies/")


@pytest.mark.django_db
def test_the_cookie_policy_names_the_cookies_this_site_really_sets(client):
    """The old page named ``django_language``; the language cookie is ``_lang`` (plan §3.a)."""
    html = client.get("/legal/cookies/").content.decode()

    for name in (
        settings.SESSION_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
        settings.COOKIE_CONSENT_NAME,
        settings.LANGUAGE_COOKIE_NAME,
    ):
        assert f"<strong>{name}</strong>" in html, name
    assert "django_language" not in html


@pytest.mark.django_db
def test_the_cookie_policy_links_the_privacy_policy_and_the_aepd_guide(client):
    html = client.get("/legal/cookies/").content.decode()

    assert f'href="{reverse("public:privacy")}"' in html
    assert "https://www.aepd.es" in html


# --- Legal notice (test_legal_notice.py) -------------------------------------------------------


@pytest.mark.django_db
def test_legal_notice_returns_200(client):
    assert client.get("/legal/legal-notice/").status_code == 200


@pytest.mark.django_db
def test_legal_notice_contains_company_data(client):
    html = client.get("/legal/legal-notice/").content.decode()

    assert "ERPLORA CLOUD S.L." in html
    assert "B27593136" in html


@pytest.mark.django_db
def test_legal_notice_gives_the_legal_contact_address(client):
    html = client.get("/legal/legal-notice/").content.decode()

    assert 'href="mailto:legal@erplora.com"' in html


# --- Privacy policy (test_privacy_es.py + test_public_pages.py) --------------------------------


@pytest.mark.django_db
def test_privacy_returns_200(client):
    assert client.get("/legal/privacy/").status_code == 200


@pytest.mark.django_db
def test_privacy_page_mentions_privacy(client):
    assert "privacy" in client.get("/legal/privacy/").content.decode().lower()


@pytest.mark.django_db
def test_privacy_contains_spanish_marker(client):
    assert "Responsable del tratamiento" in spanish(client, "/legal/privacy/")


@pytest.mark.django_db
def test_privacy_says_what_happens_to_the_payer_when_the_account_is_deleted(client):
    """ACCOUNTS-F27 (GDPR art. 17 and 17(3)(b)): the payer details and the Stripe customer go with the account;
    an unpaid ERPlora invoice holds them 90 days at most, and the issued invoices keep their own copy."""
    english = client.get("/legal/privacy/").content.decode()
    html = spanish(client, "/legal/privacy/")

    assert "Payer details" in english
    assert "Datos del pagador" in html
    assert "se borran al eliminar tu cuenta" in html
    assert "90 días" in html


@pytest.mark.django_db
def test_privacy_sections_are_numbered_consecutively(client):
    html = client.get("/legal/privacy/").content.decode()
    numbers = [int(n) for n in re.findall(r"<h2>(\d+)\.", html)]

    assert numbers, "the privacy page renders no numbered <h2> section at all"
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.django_db
def test_privacy_covers_updating_the_software_as_a_security_measure(client):
    """ADR-0269: we modify the system that processes our customer's customers' data, unilaterally.

    Art. 28.3.a GDPR says a processor acts on documented instructions. If the policy never says
    that keeping the software current is part of the instructed service — and one of the art. 32
    measures — then every update we push is processing nobody documented.
    """
    html = spanish(client, "/legal/privacy/")

    assert "artículo 32" in html
    assert "actualiza" in html


@pytest.mark.django_db
def test_privacy_says_an_update_is_not_a_change_of_sub_processor(client):
    """Art. 28.2 GDPR reserves the objection right for NEW sub-processors."""
    html = spanish(client, "/legal/privacy/")

    assert "no es un cambio de subencargado" in html
    assert "oponerse" in html


@pytest.mark.django_db
def test_privacy_declares_the_eu_resident_llm_provider_actually_in_use(client):
    """Art. 13.1.e / 28.2 GDPR: the sub-processor that actually sees the data must be named."""
    html = spanish(client, "/legal/privacy/")

    assert "Alibaba" in html
    assert "Fráncfort" in html or "Frankfurt" in html


@pytest.mark.django_db
def test_privacy_states_assistant_data_does_not_reach_china(client):
    """China has no adequacy decision (ADR-0152), so silence here reads as a Chapter V transfer."""
    html = spanish(client, "/legal/privacy/")

    assert "China" in html
    assert "no se transfieren" in html or "no salen" in html


@pytest.mark.django_db
def test_privacy_does_not_name_llm_providers_we_never_engaged(client):
    """Naming a processor we hold no credential for is a false disclosure, not a safe extra."""
    assert "DeepSeek" not in spanish(client, "/legal/privacy/")


@pytest.mark.django_db
def test_privacy_describes_what_the_assistant_actually_sends_to_the_model(client):
    """ADR-0149: no copy of the hub database, no stored conversation, only each query's result."""
    html = spanish(client, "/legal/privacy/").lower()

    assert "no se replica" in html or "no se copia" in html
    assert "no conservamos" in html or "no almacenamos" in html


@pytest.mark.django_db
def test_privacy_says_assistant_data_is_not_used_for_training(client):
    """Training on customer data is a purpose change (Art. 5.1.b) the customer never consented to."""
    html = spanish(client, "/legal/privacy/")

    assert "entrenar" in html or "entrenamiento" in html


@pytest.mark.django_db
def test_privacy_names_the_terms_of_use_and_links_the_cookie_policy(client):
    html = client.get("/legal/privacy/").content.decode()

    assert "Terms of Use" in html
    assert f'href="{reverse("public:cookies")}"' in html


# --- Where the data is hosted (Ioan, 2026-10-13: the servers are on AWS, not on Hetzner) ---------


def list_items_naming(html: str, name: str) -> list[str]:
    """The ``<li>`` of a page that mention ``name``: one processor per item in section 5."""
    return [
        item for item in re.findall(r"<li>(.*?)</li>", html, re.DOTALL) if name in item
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
@pytest.mark.parametrize(
    "provider",
    [
        "Hetzner",  # the old hosting, in Germany
        "Cloudflare",  # out since ADR-0499 (infra#253); AWS WAF + ALB + Route 53 replace it
    ],
)
def test_no_legal_page_names_a_provider_we_no_longer_use(client, path, provider):
    """Naming a processor that no longer holds the data is a false disclosure (art. 13.1.e GDPR)."""
    assert provider not in client.get(path).content.decode()
    assert provider not in spanish(client, path)


@pytest.mark.django_db
def test_privacy_names_aws_in_its_ireland_region_as_the_hosting_processor(client):
    """Hosting, database, backups, storage and the network edge (DNS, DDoS protection) are AWS's,
    Ireland region ``eu-west-1`` (Ioan, 2026-10-14: the ERP serves all of Europe; PLAN-AWS), never
    the Spain region (``eu-south-2``, Aragón) the page named before. AWS is no longer an inactive
    fallback. «España» stays in the page: it is the company's address, not where the data lives."""
    english = client.get("/legal/privacy/").content.decode()
    es = spanish(client, "/legal/privacy/")
    [hosting] = list_items_naming(english, "Data hosted in")
    [alojamiento] = list_items_naming(es, "Datos alojados en")

    assert "Amazon Web Services EMEA SARL (Luxembourg) — Ireland region, eu-west-1" in hosting
    assert "Data hosted in data centers in Ireland, within the European Union." in hosting
    assert "backups" in hosting
    assert "DDoS protection" in hosting
    assert "inactive" not in hosting
    assert "Spain" not in hosting
    assert "Amazon Web Services EMEA SARL (Luxemburgo) — región de Irlanda, eu-west-1" in alojamiento
    assert "Datos alojados en centros de datos en Irlanda, dentro de la Unión Europea." in alojamiento
    assert "copias de seguridad" in alojamiento
    assert "protección anti-DDoS" in alojamiento
    assert "España" not in alojamiento
    for html in (english, es):
        assert "eu-south-2" not in html
        assert "Aragón" not in html


@pytest.mark.django_db
def test_privacy_names_amazon_ses_in_ireland_for_transactional_email(client):
    """The transactional email goes out from Amazon SES in eu-west-1, the platform's region."""
    [email] = list_items_naming(
        client.get("/legal/privacy/").content.decode(), "Amazon SES"
    )
    [correo] = list_items_naming(spanish(client, "/legal/privacy/"), "Amazon SES")

    assert "eu-west-1" in email
    assert "Ireland" in email
    assert "Irlanda" in correo


@pytest.mark.django_db
def test_privacy_keeps_the_ai_assistant_in_frankfurt(client):
    """Only the hosting moved: the AI assistant stays in Alibaba Cloud's Frankfurt region."""
    [ai] = list_items_naming(
        client.get("/legal/privacy/").content.decode(), "Model Studio"
    )
    [ia] = list_items_naming(spanish(client, "/legal/privacy/"), "Model Studio")

    assert "Frankfurt" in ai
    assert "Fráncfort" in ia


# --- The shared reading pattern (test_ui_stack_contract.py) ------------------------------------


@pytest.mark.parametrize("template", ["legal_notice", "privacy", "cookies"])
def test_a_legal_page_uses_the_shared_public_reading_pattern(template):
    source = (LEGAL_TEMPLATES / f"{template}.html").read_text(encoding="utf-8")
    hero = next(
        line
        for line in source.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "{% block page_content %}" in source
    assert "{% block content %}" not in source
    assert "hero_compact=True" in hero
    assert 'class="ep-section--compact ep-section--divider"' in source
    assert 'class="ep-container ep-section-content"' in source
    assert 'class="ep-prose max-w-4xl mx-auto"' in source
    assert "<ion-card" not in source
    assert "max-width:" not in source
    assert 'style="' not in source
    assert "<style" not in source


# --- Links to the legal pages: footer, sitemap, llms.txt ---------------------------------------


def footer_legal_links(html: str) -> list[str]:
    begin = html.index('<span class="ep-footer__legal">')
    return re.findall(r'href="([^"]*)"', html[begin : html.index("</span>", begin)])


@pytest.mark.django_db
def test_the_footer_links_the_legal_pages_in_the_old_order(client):
    """Legal Notice, Privacy, (Terms, L7,) Cookies: the old footer's bottom bar. The declaración
    responsable joins it: art. 13.2 RRSIF wants it at hand when buying, before any account."""
    links = footer_legal_links(client.get("/legal/privacy/").content.decode())

    assert links == [
        reverse("public:legal_notice"),
        reverse("public:privacy"),
        reverse("public:terms"),
        reverse("cookie_consent_cookie_group_list"),
        reverse("public:declaracion_responsable"),
    ]


@pytest.mark.django_db
def test_the_footer_legal_links_are_translated(client):
    html = spanish(client, "/legal/privacy/")
    begin = html.index('<span class="ep-footer__legal">')
    legal = html[begin : html.index("</span>", begin)]

    assert "Aviso legal" in legal
    assert "Privacidad" in legal
    assert "Declaración responsable" in legal


@pytest.mark.parametrize(
    ("name", "priority"),
    [
        # The old sitemap listed privacy (and terms) at 0.4; the others join below it, save the
        # declaración responsable, which customers, resellers and the AEAT look up by name.
        ("public:privacy", 0.4),
        ("public:terms", 0.4),
        ("public:declaracion_responsable", 0.4),
        ("public:legal_notice", 0.3),
        ("public:cookies", 0.3),
    ],
)
def test_the_legal_pages_are_in_the_sitemap(name, priority):
    assert (name, priority) in StaticPagesSitemap.pages


@pytest.mark.django_db
def test_llms_txt_links_the_privacy_policy_as_optional_reading(client):
    body = client.get("/llms.txt", HTTP_HOST=HOST).content.decode()
    optional = body[body.index("## Optional") :]

    assert f"- [Privacy](https://{HOST}/legal/privacy/)" in optional


# --- Every message has its Spanish entry -------------------------------------------------------

_LITERAL = r"u?'(?:[^'\\]|\\.)*'|u?\"(?:[^\"\\]|\\.)*\""
#: The calls ``templatize`` writes for {% trans %} and {% blocktrans %} (what makemessages reads).
_CALL = re.compile(
    rf"\b(gettext|pgettext|ngettext|npgettext)\(((?:{_LITERAL})(?:, (?:{_LITERAL}))*)"
)


def template_messages(path: Path) -> list[str]:
    """The catalog keys of every message of a template, as ``makemessages`` would extract them."""
    source = templatize(path.read_text(encoding="utf-8"), origin=str(path))
    keys = []
    for function, arguments in _CALL.findall(source):
        literals = [ast.literal_eval(raw) for raw in re.findall(_LITERAL, arguments)]
        if function == "gettext":
            keys.append(literals[0])
        elif function == "pgettext":
            keys.append(f"{literals[0]}\x04{literals[1]}")
        elif function == "ngettext":
            keys.append((literals[0], 0))
        else:
            keys.append((f"{literals[0]}\x04{literals[1]}", 0))
    return keys


def test_the_template_messages_are_read_like_makemessages(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        '{% load i18n %}{% trans "It\'s here" %}'
        "{% blocktrans trimmed with v=x %}\n  Version\n  {{ v }}\n{% endblocktrans %}",
        encoding="utf-8",
    )

    assert template_messages(page) == ["It's here", "Version %(v)s"]


@pytest.mark.parametrize(
    "template", sorted(LEGAL_TEMPLATES.glob("*.html")), ids=lambda path: path.name
)
def test_every_message_of_a_legal_template_has_its_spanish_entry(template):
    with CATALOG.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    messages = template_messages(template)

    assert messages, f"{template.name} has no translatable message"
    assert [m for m in messages if not catalog.get(m)] == [], (
        "add the msgid/msgstr to public/locale/es/LC_MESSAGES/django.po and compile"
    )


# --- The Terms of Use (L7) -----------------------------------------------------------------------
#
# Port of apps/public/legal/tests/ (origin/develop c5ca8ca): test_terms_es.py (15),
# test_terms_exit_package.py (7), test_terms_trial_period.py (8) and test_terms_uk_business_only.py
# (7), plus the terms' reading pattern of test_ui_stack_contract.py. What changed, and why:
#
# * the trial of §4 is read from the plans on sale through hubs.plan.list (plan §3.m), not from
#   Plan.objects; the tests still create the rows with the ORM of hubs;
# * the suspension clock of §3 is public.legal.SUSPENDED_HUB_DELETE_DAYS: the task that deletes a
#   suspended hub lives in the Hub, so the number the terms print is pinned here;
# * the two marketplace sentences (§1 «modules available for purchase from a marketplace», §7.3
#   «Modules installed from the marketplace…») now speak of our own apps (spec §8.3, decision 17), and
#   the «Last updated» date moved with that change;
# * the UK example number is checked against HMRC's check digit (the «97/55» rule): the checkout's
#   validator belongs to the panel's billing (block 4) and does not exist in saas-next yet.

TERMS = "/legal/terms/"


def terms_html(client, language: str | None = None) -> str:
    if language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(TERMS).content.decode()


def make_plan(slug: str, trial_days: int, **fields):
    from decimal import Decimal

    from hubs.models import Plan

    return Plan.objects.create(
        slug=slug,
        name_en=slug.title(),
        description_en=f"{slug} plan",
        price_monthly=Decimal("29.99"),
        trial_period_days=trial_days,
        **{"is_active": True, **fields},
    )


def trial_section(client, language: str | None = None) -> str:
    """§4 of the terms, so a «15 days» elsewhere on the page cannot make a test pass."""
    match = re.search(r"<h2>\s*4\..*?<h2>\s*5\.", terms_html(client, language), re.S)
    assert match, "the terms lost their §4 / §5 headings"
    return match.group(0)


def trial_clause(section: str) -> str:
    return section.split("<li>", 1)[1].split("</li>", 1)[0]


# test_terms_es.py


@pytest.mark.django_db
def test_terms_contains_spanish_marker(client):
    assert "Condiciones de uso" in terms_html(client, "es")


@pytest.mark.django_db
def test_terms_sections_are_numbered_consecutively(client):
    """The clauses cross-reference each other by number, so a gap is a broken contract."""
    numbers = [int(n) for n in re.findall(r"<h2>(\d+)\.", terms_html(client))]

    assert numbers, "the terms page renders no numbered <h2> clause at all"
    assert numbers == list(range(1, len(numbers) + 1))


@pytest.mark.django_db
def test_terms_state_that_erplora_updates_without_asking(client):
    html = terms_html(client, "es")

    assert "7. Actualizaciones y versiones" in html
    assert "sin que el cliente tenga que solicitarlas" in html
    assert "no elige la versión que ejecuta ni puede posponer una actualización" in html


@pytest.mark.django_db
def test_terms_state_what_erplora_owes_in_exchange(client):
    html = terms_html(client, "es")

    assert "se arranca y se comprueba antes de retirar la anterior" in html
    assert "no destruye los datos del cliente ni deja el Hub con menos funciones" in html
    assert "se restaura la anterior de forma automática" in html
    assert "se anuncian antes de que entren en vigor" in html


@pytest.mark.django_db
def test_terms_do_not_promise_updates_are_optional_or_pre_notified(client):
    html = terms_html(client, "es")

    assert "no son interrupciones programadas" in html
    assert "se rigen por la cláusula 7" in html


@pytest.mark.django_db
def test_terms_say_the_customer_can_still_bring_an_update_forward(client):
    html = terms_html(client, "es")

    assert "puede adelantar una actualización" in html
    assert "Lo que no puede es posponerla" in html


@pytest.mark.django_db
def test_terms_carve_out_the_installable_app(client):
    html = terms_html(client, "es")

    assert "nunca se actualiza sola" in html
    assert "el cliente decide cuándo instalarla" in html


@pytest.mark.django_db
def test_terms_list_the_valid_reasons_for_a_unilateral_change(client):
    """Art. 85.3 TRLGDCU: without the list of valid reasons the whole of section 7 falls."""
    html = terms_html(client, "es")

    assert "motivos válidos" in html
    assert "cerrar vulnerabilidades de seguridad" in html
    assert "cambios en la normativa aplicable" in html


@pytest.mark.django_db
def test_terms_promise_an_update_never_costs_the_customer(client):
    assert "no cambia el precio del plan contratado" in terms_html(client, "es")


@pytest.mark.django_db
def test_terms_give_advance_notice_on_a_durable_medium_and_a_right_to_terminate(client):
    """Arts. 126.c/126.d + 126 bis TRLGDCU; CJEU C-375/15 (BAWAG): the email is the notice."""
    html = terms_html(client, "es")

    assert "soporte duradero" in html
    assert "treinta días naturales" in html
    assert "sin cargo alguno" in html
    assert "correo electrónico a la dirección de la cuenta" in html
    assert "no sustituye" in html
    assert "se aplican sin aviso previo" in html


@pytest.mark.django_db
def test_terms_do_not_disclaim_a_broken_update(client):
    html = terms_html(client, "es")

    assert "restablecerá la conformidad sin demora indebida" in html
    assert "reducción del precio proporcional" in html
    assert "no tiene que probar" in html


@pytest.mark.django_db
def test_terms_shield_erplora_when_the_customer_does_not_install_the_app_update(client):
    """Art. 8.3 Directive (EU) 2019/770."""
    html = terms_html(client, "es")

    assert "consecuencias de no instalarla" in html
    assert "se deba únicamente a esa actualización no instalada" in html


@pytest.mark.django_db
def test_terms_tie_updates_to_the_responsible_declaration(client):
    html = terms_html(client, "es")

    assert "declaración responsable" in html
    assert f'href="{reverse("public:declaracion_responsable")}"' in html


@pytest.mark.django_db
def test_terms_link_the_plain_language_explanation(client):
    assert f'href="{reverse("public:updates")}"' in terms_html(client, "es")


# test_terms_exit_package.py


@pytest.mark.django_db
def test_the_terms_state_the_same_number_of_days_the_code_enforces(client, settings):
    days = settings.HUB_EXIT_PACKAGE_TTL_DAYS

    assert re.search(rf"\b{days}\b[^<]*days", terms_html(client))


@pytest.mark.django_db
def test_the_terms_follow_the_exit_package_setting(client, settings):
    settings.HUB_EXIT_PACKAGE_TTL_DAYS = 45

    assert re.search(r"\b45\b[^<]*days", terms_html(client))


@pytest.mark.django_db
def test_the_terms_state_the_suspension_clock(client):
    from public.legal import SUSPENDED_HUB_DELETE_DAYS

    html = terms_html(client)

    assert re.search(rf"\b{SUSPENDED_HUB_DELETE_DAYS}\b[^<]*days", html)
    assert "permanent cancellation after 30 days" not in html


@pytest.mark.django_db
def test_the_terms_say_what_is_delivered_when_a_hub_is_deleted(client):
    html = terms_html(client).lower()

    assert "database" in html
    assert "files" in html
    assert "encrypted" in html


@pytest.mark.django_db
def test_the_terms_say_that_afterwards_there_is_no_recovery(client):
    assert "cannot be recovered" in terms_html(client).lower()


@pytest.mark.django_db
def test_the_terms_put_the_legal_retention_on_the_customer(client):
    html = terms_html(client)

    assert "6 years" in html
    assert "Commercial Code" in html
    assert "30 days to export" not in html


@pytest.mark.django_db
def test_a_spanish_customer_reads_the_exit_package_in_spanish(client, settings):
    html = terms_html(client, "es")

    assert str(settings.HUB_EXIT_PACKAGE_TTL_DAYS) in html
    assert "no se puede recuperar" in html.lower()
    assert "Código de Comercio" in html


# test_terms_trial_period.py


@pytest.mark.django_db
def test_the_terms_state_the_trial_length_the_checkout_grants(no_plans, client):
    make_plan("free", 0)
    make_plan("starter", 15)
    make_plan("standard", 15)

    section = trial_section(client)

    assert re.search(r"\b15 days\b", section)
    assert "6 months" not in section
    assert re.findall(r"\d+", trial_clause(section)) == ["15"]


@pytest.mark.django_db
def test_the_terms_follow_the_plan_when_its_trial_changes(no_plans, client):
    make_plan("starter", 30)

    section = trial_section(client)

    assert re.search(r"\b30 days\b", section)
    assert not re.search(r"\b15 days\b", section)


@pytest.mark.django_db
def test_plans_a_visitor_cannot_buy_do_not_count_in_the_terms(no_plans, client):
    make_plan("starter", 15)
    make_plan("internal", 90, internal_only=True)
    make_plan("retired", 180, is_active=False)

    section = trial_section(client)

    assert re.search(r"\b15 days\b", section)
    assert "90" not in section and "180" not in section


@pytest.mark.django_db
def test_plans_with_different_trials_are_stated_as_a_range_in_the_terms(no_plans, client):
    make_plan("starter", 15)
    make_plan("standard", 30)

    assert re.search(r"\b15\b[^<]*\b30 days\b", trial_section(client))


@pytest.mark.django_db
def test_no_trial_on_sale_means_no_trial_promised_in_the_terms(no_plans, client):
    make_plan("free", 0)
    make_plan("starter", 0)

    section = trial_section(client)

    assert "trial" not in section.split("</h2>", 1)[1].split("</li>", 1)[0].lower()
    assert "cancel the subscription at any time" in section


@pytest.mark.django_db
def test_a_spanish_customer_reads_the_trial_in_spanish(no_plans, client):
    make_plan("starter", 15)

    section = trial_section(client, "es")

    assert re.search(r"\b15 días\b", section)
    assert "6 meses" not in section


@pytest.mark.django_db
def test_a_plan_reached_only_by_upgrading_does_not_count_in_the_terms(no_plans, client):
    make_plan("starter", 15)
    make_plan("pro", 30, upgrade_only=True)

    section = trial_section(client)

    assert re.search(r"\b15 days\b", section)
    assert "30" not in section


@pytest.mark.django_db
def test_the_trial_is_promised_on_hub_creation_and_not_on_an_upgrade(no_plans, client):
    make_plan("starter", 15)

    english = trial_clause(trial_section(client))
    spanish_clause = trial_clause(trial_section(client, "es"))

    assert "when creating a Hub" in english
    assert "does not start a new trial" in english
    assert "al crear un Hub" in spanish_clause
    assert "no inicia un nuevo periodo de prueba" in spanish_clause


# test_terms_uk_business_only.py


def uk_clause(html: str) -> str:
    match = re.search(r'<section[^>]*id="united-kingdom"[^>]*>(.*?)</section>', html, re.S)
    assert match, "the terms have no United Kingdom clause (id=united-kingdom)"
    return match.group(1)


def hmrc_check_digit_is_valid(number: str) -> bool:
    """HMRC's check digit of a 9-digit VAT number: weights 8..2, then «97» or «97-55»."""
    digits = [int(char) for char in number[2:]]
    total = sum(digit * weight for digit, weight in zip(digits[:7], range(8, 1, -1)))
    check = digits[7] * 10 + digits[8]
    return (total + check) % 97 == 0 or (total + check + 55) % 97 == 0


def test_the_hmrc_check_tells_a_good_number_from_a_typo():
    """Positive control of the check below."""
    assert hmrc_check_digit_is_valid("GB123456782")
    assert not hmrc_check_digit_is_valid("GB123456783")


@pytest.mark.django_db
def test_the_terms_have_a_united_kingdom_clause(client):
    clause = uk_clause(terms_html(client))

    assert "United Kingdom" in clause
    assert "VAT" in clause


@pytest.mark.django_db
def test_the_example_uk_vat_number_is_a_valid_one(client):
    examples = re.findall(r"\b(?:GB|XI)\d{9}\b", uk_clause(terms_html(client)))

    assert examples, "the clause has to show what a UK VAT number looks like"
    assert all(hmrc_check_digit_is_valid(example) for example in examples)


@pytest.mark.django_db
def test_the_uk_clause_is_limited_to_paid_services(client):
    clause = uk_clause(terms_html(client)).lower()

    assert "paid" in clause
    assert "free plan" in clause


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "sells", "old"),
    [
        (
            "en",
            "In the United Kingdom, ERPlora sells its paid plans only to businesses, for use in the "
            "course of their business.",
            "plans and modules",
        ),
        (
            "es",
            "En Reino Unido, ERPlora vende sus planes de pago solo a empresas y profesionales, para "
            "el ejercicio de su actividad.",
            "planes y módulos",
        ),
    ],
)
def test_the_uk_clause_sells_plans_not_modules(client, language, sells, old):
    """Our modules are not sold on their own: every plan includes all the apps (ronda 2026-10-24b,
    PLAN §32). The clause said «its paid plans and modules»."""
    clause = uk_clause(terms_html(client, language))

    assert sells in clause
    assert old not in clause


@pytest.mark.django_db
def test_the_uk_clause_is_translated_into_spanish(client):
    english = uk_clause(terms_html(client))
    spanish_clause = uk_clause(terms_html(client, "es"))

    assert "Reino Unido" in spanish_clause
    heading = re.search(r"<h3>(.*?)</h3>", english).group(1)
    assert heading not in spanish_clause


@pytest.mark.django_db
def test_the_terms_date_moved_with_the_last_change(client):
    """The page says when its text last changed: the marketplace sentences (L7), then §1 and §3.1,
    every app on every plan and no module sold on its own (ronda 2026-10-24b, PLAN §32)."""
    html = terms_html(client)
    spanish = terms_html(client, "es")

    for old in ("August 8, 2026", "October 1, 2026", "October 13, 2026"):
        assert old not in html, old
    assert "<strong>Last updated:</strong> October 25, 2026" in html
    assert "13 de octubre de 2026" not in spanish
    assert "25 de octubre de 2026" in spanish


@pytest.mark.django_db
def test_a_business_that_is_not_vat_registered_has_a_way_in(client):
    clause = uk_clause(terms_html(client))

    assert "registered for VAT in the United Kingdom, for use" not in clause
    assert "website" in clause
    assert "declare" in clause


@pytest.mark.django_db
def test_the_way_in_is_translated_into_spanish(client):
    spanish_clause = uk_clause(terms_html(client, "es"))

    assert "web" in spanish_clause
    assert "website" not in spanish_clause


# Our apps, not a marketplace (spec §8.3), and all of them on every plan (ronda 2026-10-24b, PLAN §32)


@pytest.mark.django_db
def test_the_terms_speak_of_our_apps_not_of_a_marketplace(client):
    for language in ("en", "es"):
        assert "marketplace" not in terms_html(client, language).lower(), language
    english = terms_html(client, "en")
    assert "a catalogue of apps of its own" in english
    assert "The apps turned on in the Hub are updated under these same rules." in english
    spanish_terms = terms_html(client, "es")
    assert "un catálogo de apps propias" in spanish_terms
    assert "Las apps activadas en el Hub se actualizan con estas mismas reglas." in spanish_terms


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "clause"),
    [
        (
            "en",
            "ERPlora offers a modular, multi-tenant ERP/POS SaaS platform, deployed on European "
            "cloud infrastructure, with features such as sales, inventory, and customer "
            "management, invoicing, tax integrations (VeriFactu), and a catalogue of apps of its "
            "own that the customer turns on in their Hub: every plan includes all the apps.",
        ),
        (
            "es",
            "ERPlora ofrece una plataforma SaaS multi-tenant tipo ERP/POS, modular, desplegada en "
            "infraestructura cloud europea, con funcionalidades como gestión de ventas, "
            "inventario, clientes, facturación, integraciones fiscales (VeriFactu) y un catálogo "
            "de apps propias que el cliente activa en su Hub: todos los planes incluyen todas las "
            "apps.",
        ),
    ],
)
def test_the_service_clause_puts_every_app_on_every_plan(client, language, clause):
    """§1 said «the free apps come with every plan, and the premium apps are included in the paid
    plans»: every plan includes all the apps now (PLAN §32), and the rest of the terms is untouched."""
    html = terms_html(client, language)

    assert clause in html
    assert "premium" not in html.lower()


# The shared reading pattern (test_ui_stack_contract.py)


def test_terms_of_use_uses_the_shared_public_reading_pattern():
    terms = (LEGAL_TEMPLATES / "terms.html").read_text(encoding="utf-8")

    assert "hero_compact=True" in terms
    assert 'class="ep-section--compact ep-section--divider"' in terms
    assert 'class="ep-container ep-section-content"' in terms
    assert 'class="ep-prose max-w-4xl mx-auto"' in terms
    assert "<ion-card" not in terms
    assert "max-width:" not in terms
    assert 'style="' not in terms
    assert "<style" not in terms
