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
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from django.utils.translation.template import templatize

from accounts.models import PRIVACY_VERSION, TERMS_VERSION
from hubs.tests.test_plan_catalogue import APP_ON_A_CUSTOM_DOMAIN, CUSTOM_DOMAIN_WORDS
from public.sitemaps import StaticPagesSitemap
from public.tests.conftest import without_tokens

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
        # No voice of the server: reading aloud is the device's, and no text goes to Azure AI Speech (it left, saas#242).
        "Microsoft Ireland Operations",
        "Azure",
    ],
)
def test_no_legal_page_names_a_provider_we_no_longer_use(client, path, provider, tokens_spelling):
    """Naming a processor that no longer holds the data is a false disclosure (art. 13.1.e GDPR)."""
    tokens_spelling("Hetzner", "Cloudflare", "Azure")
    assert provider not in without_tokens(client.get(path).content.decode())
    assert provider not in without_tokens(spanish(client, path))


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


# --- The assistant's voice and search fingerprints (FIX-SAAS-PRIVACY-POLICY-OMITS-DICTATION-AUDIO-TO-TRANSCRIPTION) 
# ``assistant/media.py`` sends two services to the provider of ``ASSISTANT_SERVICE_PROVIDER`` (OpenAI's API at
# ``api.openai.com`` by default), none of them the backup model: the transcription of a dictation (``whisper-1``, the
# audio of the recording) and the fingerprints of the Hub's index (``text-embedding-3-small``). Reading an answer aloud
# is the device's own voice (the browser's or the system's): erplora.com has no voice of its own (no engine behind its
# door, saas#242), so no processor receives that text. Google Play checks the app's
# «Data safety › Audio» against this page (app#4).

VOICE_PROVIDER = "OpenAI Ireland Ltd. ("

VOICE_SERVICES = {
    "en": (
        "BY DEFAULT",
        "transcribes voice dictation into text (it receives the audio of the recording)",
        "computes the search fingerprints, or embeddings",
        "outside the European Economic Area",
    ),
    "es": (
        "POR DEFECTO",
        "transcribe a texto el dictado por voz (recibe el audio de la grabación)",
        "calcula las huellas de búsqueda (embeddings)",
        "fuera del Espacio Económico Europeo",
    ),
}


def privacy(client, language: str) -> str:
    return spanish(client, "/legal/privacy/") if language == "es" else client.get("/legal/privacy/").content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_names_the_default_provider_of_the_assistant_voice_and_search_fingerprints(client, language):
    """Art. 13.1.e GDPR: the processor that receives a dictation's audio is named, with what it receives."""
    [voice] = list_items_naming(privacy(client, language), VOICE_PROVIDER)

    assert [claim for claim in VOICE_SERVICES[language] if claim.lower() not in voice.lower()] == []


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_names_no_provider_that_reads_answers_aloud(client, language):
    """Art. 13.1.e GDPR: nobody receives the text of an answer read aloud, so no processor is named for it, and OpenAI
    only transcribes and computes the fingerprints."""
    html = privacy(client, language)
    [voice] = list_items_naming(html, VOICE_PROVIDER)

    assert "aloud" not in voice and "voz alta" not in voice
    for server_voice in ("server's voice", "voz del servidor", "speech provider", "proveedor de voz"):
        assert server_voice not in html


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "marker", "claims"),
    [
        (
            "en",
            "Reading aloud:",
            (
                "the answer is read by your device's own voice (the browser's or the system's)",
                "its text never leaves the device",
            ),
        ),
        (
            "es",
            "Lectura en voz alta:",
            (
                "la respuesta la lee la voz de tu propio dispositivo (la del navegador o la del sistema)",
                "su texto no sale de él",
            ),
        ),
    ],
)
def test_privacy_says_an_answer_read_aloud_never_leaves_the_device(client, language, marker, claims):
    """The panel and the Hub read with the device's voice (``spa-config.assistantSpeech`` false, base/spa.py): the
    text is not sent anywhere, and nothing is counted."""
    [reading] = list_items_naming(privacy(client, language), marker)

    assert [claim for claim in claims if claim not in " ".join(reading.split())] == []
    for gone in ("characters", "caracteres", "platform", "plataforma"):
        assert gone not in reading


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_promises_no_residency_or_retention_the_voice_provider_does_not_give(client, language):
    """``api.openai.com`` keeps no data in the EU by contract, and how long it keeps a request is set by its API terms,
    not by our code: the item promises neither."""
    [voice] = list_items_naming(privacy(client, language), VOICE_PROVIDER)

    for promise in ("takes place in the European Union", "se realiza en la Unión Europea", "days", "días", "zero", "cero"):
        assert promise not in voice


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "marker", "claims"),
    [
        (
            "en",
            "Voice dictation:",
            ("to the transcription provider", "only its text comes back", "Neither your hub nor ERPlora keeps the audio"),
        ),
        (
            "es",
            "Dictado por voz:",
            ("al proveedor de transcripción", "solo vuelve su texto", "Ni tu hub ni ERPlora guardan el audio"),
        ),
    ],
)
def test_privacy_says_where_the_dictation_audio_goes_and_that_nobody_here_keeps_it(client, language, marker, claims):
    """The Hub's operation opens no database (``database=False``) and erplora.com passes the audio from memory to the
    provider (``assistant/media.py``): only a count of the dictation stays, in the month's usage."""
    [dictation] = list_items_naming(privacy(client, language), marker)

    assert [claim for claim in claims if claim not in dictation] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "model", "outside", "voice"),
    [
        (
            "en",
            "The language model of the AI assistant is served from",
            "Some processors may process data outside the EEA",
            "the provider of the voice and search fingerprint services of the assistant",
        ),
        (
            "es",
            "El modelo de lenguaje del asistente IA se sirve desde",
            "Algunos encargados pueden tratar datos fuera del EEE",
            "el proveedor de los servicios de voz y de huellas de búsqueda del asistente",
        ),
    ],
)
def test_privacy_counts_the_voice_provider_among_the_transfers_outside_the_eea(client, language, model, outside, voice):
    """Section 6: Frankfurt serves the language model, not the dictation, and the voice provider is a transfer."""
    paragraphs = [" ".join(text.split()) for text in re.findall(r"<p>(.*?)</p>", privacy(client, language), re.DOTALL)]
    [transfers] = [text for text in paragraphs if outside in text]

    assert [text for text in paragraphs if model in text]
    assert voice in transfers


# --- The assistant's web search: Brave Search (ASSISTANT-F14, saas#277) ----------------------------------------------
#
# Brave leaves the queries out of its data processing addendum and keeps them up to 90 days (its privacy notice, dated
# 2026-11-03), so it is named as what it is: a recipient of its own, not one of the art. 28 processors of section 5, and
# not under the Standard Contractual Clauses of section 6. Nothing may promise that a query never carries personal data:
# that is a rule given to the model (``assistant.server_tools._SEARCH_QUERY_RULE``), no guarantee.

WEB_SEARCH_PROVIDER = "Brave Software, Inc."

WEB_SEARCH_RECIPIENT = {
    "en": (
        "Brave Search API",
        "United States",
        "NOT one of the processors above",
        "leaves the search queries out",
        "the text of the query",
        "nothing that says who asks",
        "for up to 90 days",
    ),
    "es": (
        "Brave Search API",
        "Estados Unidos",
        "NO es uno de los encargados anteriores",
        "deja fuera las consultas de búsqueda",
        "el texto de la consulta",
        "nada que diga quién pregunta",
        "hasta 90 días",
    ),
}

WEB_SEARCH_TRANSFER = {
    "en": ("Some processors may process data outside the EEA", ("United States", "do not cover them")),
    "es": ("Algunos encargados pueden tratar datos fuera del EEE", ("Estados Unidos", "no las cubren")),
}

WEB_SEARCH_RULE = {
    "en": ("Web search:", "not a guarantee", "An automation never searches"),
    "es": ("Búsqueda en la web:", "no una garantía", "Una automatización nunca busca"),
}

#: What only a guarantee could say of a query the model writes.
WEB_SEARCH_PROMISES = {
    "en": ("never carries", "never contains", "never includes", "no personal data reaches", "no personal data is sent"),
    "es": ("nunca lleva", "nunca contiene", "nunca incluye", "ningún dato personal llega", "no se envía ningún dato personal"),
}

#: The fingerprints of the hub's index are OpenAI's, and the words that told them from nothing now read as the web search.
AMBIGUOUS_SEARCH_SERVICES = {"en": "voice and search services", "es": "servicios de voz y de búsqueda"}


def section(html: str, number: int) -> str:
    """Section ``number`` of a legal page, up to the next heading."""
    match = re.search(rf"<h2>{number}\. .*?</h2>(.*?)(?=<h2>|</article>)", html, re.S)
    assert match, f"the page has no section {number}"
    return match.group(1)


def paragraphs_of(html: str) -> list[str]:
    return [" ".join(text.split()) for text in re.findall(r"<p>(.*?)</p>", html, re.DOTALL)]


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_names_brave_with_what_it_receives_and_keeps(client, language):
    """Art. 13.1.e GDPR: whoever receives the queries is named, with what it receives and how long it keeps it."""
    [search] = list_items_naming(privacy(client, language), WEB_SEARCH_PROVIDER)
    search = " ".join(search.split())

    assert [claim for claim in WEB_SEARCH_RECIPIENT[language] if claim not in search] == []


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_does_not_count_brave_among_the_art_28_processors(client, language):
    """Its addendum leaves the queries out: under «with whom we have signed Art. 28 GDPR agreements» it would be false."""
    recipients = section(privacy(client, language), 5)
    before, processors = re.search(r"(.*?)<ul>(.*?)</ul>", recipients, re.S).groups()

    assert "28" in before
    assert "Amazon Web Services" in processors
    assert "Brave" not in processors
    assert WEB_SEARCH_PROVIDER in recipients


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_does_not_put_the_web_search_under_the_standard_contractual_clauses(client, language):
    """Section 6: the clauses are in the addendum that leaves the queries out, so they cannot cover them."""
    outside, says = WEB_SEARCH_TRANSFER[language]
    paragraphs = paragraphs_of(section(privacy(client, language), 6))
    [transfers] = [text for text in paragraphs if outside in text]
    [web_search] = [text for text in paragraphs if WEB_SEARCH_PROVIDER in text]

    assert "Brave" not in transfers
    assert [claim for claim in says if claim not in web_search] == []


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_does_not_promise_a_query_never_carries_personal_data(client, language):
    """The rule is told to a model: a policy that promised its result would be false the day it failed."""
    html = privacy(client, language)
    marker, *claims = WEB_SEARCH_RULE[language]
    [rule] = list_items_naming(html, marker)
    rule = " ".join(rule.split())

    assert [claim for claim in claims if claim not in rule] == []
    assert [promise for promise in WEB_SEARCH_PROMISES[language] if promise in " ".join(html.split())] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "scoped"),
    [
        ("en", "None of the processors above uses the data to train their models"),
        ("es", "Ninguno de los encargados anteriores utiliza los datos para entrenar sus modelos"),
    ],
)
def test_privacy_rests_its_no_training_promise_on_the_terms_only_for_the_processors(client, language, scoped):
    """Brave's terms do not say it: its API page does, and the policy says so of Brave in those words (section 5)."""
    assert scoped in " ".join(privacy(client, language).split())


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_tells_the_search_fingerprints_from_the_web_search(client, language):
    """«Search services» was OpenAI's only while the assistant had no web search."""
    assert AMBIGUOUS_SEARCH_SERVICES[language] not in " ".join(privacy(client, language).split())


def test_the_search_the_assistant_calls_is_the_one_the_policy_names():
    """Another provider of the web search is another recipient: this falls before the policy can go stale."""
    assert urlsplit(settings.ASSISTANT_SEARCH_URL).hostname.endswith(".brave.com")


@pytest.mark.django_db
def test_the_privacy_date_moved_with_the_last_change(client):
    """The version an account accepts is the date of the page (``accounts/tests/test_terms.py`` keeps them equal):
    naming Brave is a new text, so both move, and every account accepts it at its next sign-in."""
    assert PRIVACY_VERSION > date(2026, 11, 3)
    assert "November 3, 2026" not in privacy(client, "en")
    assert "3 de noviembre de 2026" not in privacy(client, "es")


# The dictation of the account's panel reaches the same provider without a hub in the way (ASSISTANT-F21, saas#175).
PANEL_DICTATION = {
    "en": {
        "voice": "Used ONLY when someone in your hub, or in the assistant of your account's panel on erplora.com, uses one of these functions",
        "route": "through your hub if you dictate there",
    },
    "es": {
        "voice": "Usado ÚNICAMENTE cuando alguien de tu hub, o en el asistente del panel de tu cuenta en erplora.com, usa una de estas funciones",
        "route": "a través de tu hub si dictas allí",
    },
}


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "marker"), [("en", "Voice dictation:"), ("es", "Dictado por voz:")])
def test_privacy_counts_the_dictation_of_the_account_panel(client, language, marker):
    """Art. 13.1.e GDPR: the panel's microphone sends the audio to the voice provider too, so «ONLY from your hub» would
    be false, and its route to the provider has no hub in it."""
    html = privacy(client, language)
    [voice] = list_items_naming(html, VOICE_PROVIDER)
    [dictation] = list_items_naming(html, marker)

    assert PANEL_DICTATION[language]["voice"] in " ".join(voice.split())
    assert PANEL_DICTATION[language]["route"] in " ".join(dictation.split())


# What decides that the assistant is used: the Hub has no switch for it and asks for no consent. Anyone with
# ``base.view_home`` sees its button (hub ``base/frontend/components/TopbarChrome.vue``), it is used when someone sends
# it a message or dictates, and the plan's monthly messages (``Plan.assistant_messages_per_month``, 0 = none;
# ``assistant/queries.py`` ``monthly_limit``) bound the questions that reach the model. The account's panel on
# erplora.com has an assistant of its own (ASSISTANT-F25), with the same chat and the same dictation (ASSISTANT-F21).

ASSISTANT_CONDITION = {
    "en": {
        "promises": ("explicit consent in the Hub", "does not enable it", "the customer enables"),
        "condition": (
            "it is used only when someone sends a message or dictates to the assistant of your hub or of your account's panel on erplora.com",
            "A plan without assistant messages sends no question to the model",
        ),
        "basis": "Used ONLY when someone uses the assistant of your hub or of your account's panel on erplora.com, to provide the contracted service (Art. 6.1.b GDPR)",
    },
    "es": {
        "promises": ("consentimiento explícito en el Hub", "no lo activa", "el cliente activa"),
        "condition": (
            "solo se usa cuando alguien envía un mensaje o dicta al asistente de tu hub o al del panel de tu cuenta en erplora.com",
            "Un plan sin mensajes del asistente no envía ninguna pregunta al modelo",
        ),
        "basis": "Usado ÚNICAMENTE cuando alguien usa el asistente de tu hub o el del panel de tu cuenta en erplora.com, para prestar el servicio contratado (Art. 6.1.b RGPD)",
    },
}


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_promises_no_switch_nor_consent_the_hub_lacks_and_says_when_the_assistant_is_used(client, language):
    """Art. 13 GDPR: the policy describes the processing as it is; a consent the Hub never asks for and a switch it
    does not have are false statements, however reassuring."""
    expected = ASSISTANT_CONDITION[language]
    html = " ".join(privacy(client, language).split())
    [model] = list_items_naming(html, "Model Studio")

    assert [promise for promise in expected["promises"] if promise in html] == []
    assert [condition for condition in expected["condition"] if condition not in html] == []
    assert expected["basis"] in model


# --- The shared reading pattern (test_ui_stack_contract.py) ------------------------------------


#: What a page with a date extends: the reading pattern and where the date goes.
DATED_PAGE = 'extends "public/legal/_dated_page.html"'


@pytest.mark.parametrize("template", ["legal_notice", "privacy", "cookies", "terms"])
def test_a_legal_page_uses_the_shared_public_reading_pattern(template):
    source = (LEGAL_TEMPLATES / f"{template}.html").read_text(encoding="utf-8")
    shared = (LEGAL_TEMPLATES / "_dated_page.html").read_text(encoding="utf-8") if DATED_PAGE in source else source
    hero = next(
        line
        for line in source.splitlines()
        if 'include "public/partials/page_hero.html"' in line
    )

    assert "{% block page_content %}" in shared
    assert "{% block content %}" not in source
    assert "hero_compact=True" in hero
    assert 'class="ep-section--compact ep-section--divider"' in shared
    assert 'class="ep-container ep-section-content"' in shared
    assert 'class="ep-prose max-w-4xl mx-auto"' in shared
    for html in (source, shared):
        assert "<ion-card" not in html
        assert "max-width:" not in html
        assert 'style="' not in html
        assert "<style" not in html


@pytest.mark.parametrize("template", ["privacy", "terms", "cookies"])
def test_a_dated_legal_page_says_its_date_in_the_one_place(template):
    """Of the terms and the privacy policy, that date is the version an account accepts (``accounts/models.py``)."""
    source = (LEGAL_TEMPLATES / f"{template}.html").read_text(encoding="utf-8")

    assert DATED_PAGE in source
    assert "{% block updated %}" in source
    assert "Last updated:" not in source


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
#: The calls ``templatize`` writes for {% trans %}, {% blocktrans %} and a ``_("…")`` argument of a tag, such as the
#: label of a {% button %} (what makemessages reads).
_CALL = re.compile(
    rf"\b(gettext|pgettext|ngettext|npgettext|_)\(((?:{_LITERAL})(?:, (?:{_LITERAL}))*)"
)


def template_messages(path: Path) -> list[str]:
    """The catalog keys of every message of a template, as ``makemessages`` would extract them."""
    source = templatize(path.read_text(encoding="utf-8"), origin=str(path))
    keys = []
    for function, arguments in _CALL.findall(source):
        literals = [ast.literal_eval(raw) for raw in re.findall(_LITERAL, arguments)]
        if function in ("gettext", "_"):
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
        "{% blocktrans trimmed with v=x %}\n  Version\n  {{ v }}\n{% endblocktrans %}"
        '{% button href="/launch" label=_("It\'s a button") %}',
        encoding="utf-8",
    )

    assert template_messages(page) == ["It's here", "Version %(v)s", "It's a button"]


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


#: What Brave's terms, §4(c), ask each end user to agree to: obligations substantially like those of §3(b).
WEB_RESULTS_RESTRICTIONS = {
    "en": (
        "web results the AI assistant brings",
        "Store, cache, or build a database",
        "derivative works",
        "redistribute, resell, or sublicense",
        "train",
        "get around the limits on searches",
    ),
    "es": (
        "resultados de la web que trae el asistente IA",
        "Guardar, almacenar en caché o crear una base de datos",
        "obras derivadas",
        "redistribuirlos, revenderlos o sublicenciarlos",
        "entrenar",
        "saltarse los límites de búsquedas",
    ),
}


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_terms_bind_the_customer_to_what_the_search_provider_asks_of_its_results(client, language):
    """Brave's terms, §4(c): each end user is bound in writing to something like §3(b); acceptable use is where breach
    means suspension, as §4(c) also asks."""
    [clause] = list_items_naming(section(terms_html(client, language), 8), WEB_RESULTS_RESTRICTIONS[language][0])
    clause = " ".join(clause.split())

    assert [claim for claim in WEB_RESULTS_RESTRICTIONS[language] if claim not in clause] == []


@pytest.mark.django_db
def test_terms_contains_spanish_marker(client):
    assert "Condiciones de uso" in terms_html(client, "es")


@pytest.mark.django_db
def test_terms_sections_are_numbered_consecutively(client):
    """The clauses cross-reference each other by number, so a gap is a broken contract."""
    numbers = [int(n) for n in re.findall(r"<h2>(\d+)\.", terms_html(client))]

    assert numbers, "the terms page renders no numbered <h2> clause at all"
    assert numbers == list(range(1, len(numbers) + 1))


#: What the terms say of the custom domain (HUBS-F17, saas#301): on the plans that include one, read from their rows,
#: and only the public website; the app and the way in stay on erplora.com (PLAN-SAAS §37 point 2).
CUSTOM_DOMAIN_TERMS = {
    "en": (
        "On the Standard, Pro, Enterprise and Max plans, the customer's public website can also be served on "
        "their own domain; the application and access to the business stay on erplora.com."
    ),
    "es": (
        "En los planes Standard, Pro, Enterprise y Max, la web pública del cliente también puede servirse en un "
        "dominio propio; la aplicación y la entrada al negocio siguen en erplora.com."
    ),
}


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_terms_name_the_plans_that_include_a_custom_domain(client, language):
    """§1 named «the customer's own domains» before any could be connected (saas#233 took it out); since saas#302
    they can, on the plans whose ``includes_custom_domain`` is true, and only for the public website."""
    html = terms_html(client, language)

    assert CUSTOM_DOMAIN_TERMS[language] in paragraphs_of(html)
    assert APP_ON_A_CUSTOM_DOMAIN.search(html) is None


@pytest.mark.django_db
def test_the_terms_follow_the_rows_of_the_plans(client):
    from hubs.models import Plan

    Plan.objects.exclude(slug="standard").update(includes_custom_domain=False)

    assert CUSTOM_DOMAIN_TERMS["en"].replace("Standard, Pro, Enterprise and Max plans", "Standard plan") in paragraphs_of(
        terms_html(client)
    )


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_without_a_plan_that_includes_it_the_terms_name_no_custom_domain(client, language):
    """saas#233's guard, now tied to the gate: no plan on sale with one, no custom domain in the terms."""
    from hubs.models import Plan

    Plan.objects.update(includes_custom_domain=False)
    html = terms_html(client, language)

    match = CUSTOM_DOMAIN_WORDS.search(html)
    assert match is None, html[max(0, match.start() - 120) : match.end() + 40]


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
    every app on every plan and no module sold on its own (ronda 2026-10-24b, PLAN §32), then §1 again,
    no customer's own domain (saas#233), then §8, the web results of the assistant (saas#277), and the same day the
    opening clause, the plans that include an own domain (saas#301)."""
    html = terms_html(client)
    spanish = terms_html(client, "es")

    for old in ("August 8, 2026", "October 1, 2026", "October 13, 2026", "October 25, 2026", "November 3, 2026"):
        assert old not in html, old
    assert TERMS_VERSION > date(2026, 11, 3)
    assert "25 de octubre de 2026" not in spanish
    assert "3 de noviembre de 2026" not in spanish


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
def test_the_service_clause_puts_every_app_on_every_plan(client, language, clause, tokens_spelling):
    """§1 said «the free apps come with every plan, and the premium apps are included in the paid
    plans»: every plan includes all the apps now (PLAN §32), and the rest of the terms is untouched."""
    tokens_spelling("premium")
    html = without_tokens(terms_html(client, language))

    assert clause in html
    assert "premium" not in html.lower()


# The shared reading pattern (test_ui_stack_contract.py)


