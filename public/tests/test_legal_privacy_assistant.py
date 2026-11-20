"""What the privacy policy says of the AI assistant: who receives its dictation and its search fingerprints, who
receives its web searches, and when the assistant is used.
"""

import re
from datetime import date
from urllib.parse import urlsplit

import pytest
from django.conf import settings

from accounts.models import PRIVACY_VERSION
from public.tests.legal_pages import list_items_naming, paragraphs_of, section, spanish


# --- The assistant's voice and search fingerprints ----------------------------------------------------------------
# ``assistant/media.py`` sends two services to the provider of ``ASSISTANT_SERVICE_PROVIDER`` (OpenAI's API at
# ``api.openai.com`` by default), none of them the backup model: the transcription of a dictation (``whisper-1``, the
# audio of the recording) and the fingerprints of the Hub's index (``text-embedding-3-small``). Reading an answer aloud
# is the device's own voice (the browser's or the system's): erplora.com has no voice of its own, so no processor
# receives that text. Google Play checks the app's «Data safety › Audio» against this page.

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


def transfer_paragraphs(client, language: str) -> list[str]:
    return [" ".join(text.split()) for text in re.findall(r"<p>(.*?)</p>", privacy(client, language), re.DOTALL)]


# Section 6 as the provider of the default model publishes it (its commercial terms, its data processing addendum, its
# privacy centre and the API's data residency page, read on 2026-11-20): traffic may go to the United States, Europe,
# Asia and Australia, the data is stored in the United States, there is no EU-only option, and the addendum, part of
# its terms, brings the Standard Contractual Clauses, modules two and three.
DEFAULT_MODEL_TRANSFER = {
    "en": (
        "The language model the AI assistant uses by default is Anthropic's.",
        "the United States, Europe, Asia and Australia",
        "stores the data in the United States",
        "so they are transferred outside the EEA",
        "Standard Contractual Clauses (modules two and three)",
    ),
    "es": (
        "El modelo de lenguaje que el asistente IA usa por defecto es el de Anthropic.",
        "Estados Unidos, Europa, Asia y Australia",
        "guarda los datos en Estados Unidos",
        "así que se transfieren fuera del EEE",
        "Cláusulas Contractuales Tipo (módulos dos y tres)",
    ),
}


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "es"])
def test_privacy_says_where_the_default_model_takes_the_queries_and_under_what(client, language):
    """Art. 13.1.f GDPR: a transfer outside the EEA and its safeguard are stated; no other framework is claimed."""
    claims = DEFAULT_MODEL_TRANSFER[language]
    [transfer] = [text for text in transfer_paragraphs(client, language) if claims[0] in text]

    assert [claim for claim in claims if claim not in transfer] == []
    assert "Privacy Framework" not in privacy(client, language)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "backup", "voice"),
    [
        (
            "en",
            "The backup language model is served from Alibaba Cloud Model Studio's Germany (Frankfurt) region",
            "The provider of the voice and search fingerprint services of the assistant may also process data outside the EEA",
        ),
        (
            "es",
            "El modelo de lenguaje de respaldo se sirve desde la región Alemania (Fráncfort) de Alibaba Cloud Model Studio",
            "El proveedor de los servicios de voz y de huellas de búsqueda del asistente también puede tratar datos fuera del EEE",
        ),
    ],
)
def test_privacy_counts_the_voice_provider_among_the_transfers_outside_the_eea(client, language, backup, voice):
    """Section 6: Frankfurt serves the backup model, not the dictation, and the voice provider is a transfer too."""
    paragraphs = transfer_paragraphs(client, language)

    assert [text for text in paragraphs if backup in text]
    assert [text for text in paragraphs if voice in text]


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "stale"), [("en", "European provider"), ("es", "proveedor europeo")])
def test_privacy_no_longer_calls_the_default_model_the_european_one(client, language, stale):
    assert stale not in privacy(client, language)


# --- The assistant's web search: Brave Search ------------------------------------------------------------------------
#
# Brave leaves the queries out of its data processing addendum and keeps them up to 90 days (its privacy notice
# of 2026-11-03), so it is named as what it is: its own recipient, not one of the art. 28 processors of section 5, and
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
    "en": ("may also process data outside the EEA", ("United States", "do not cover them")),
    "es": ("también puede tratar datos fuera del EEE", ("Estados Unidos", "no las cubren")),
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
    """«Search services» alone no longer names OpenAI's fingerprints, now that the assistant also searches the web."""
    assert AMBIGUOUS_SEARCH_SERVICES[language] not in " ".join(privacy(client, language).split())


def test_the_search_the_assistant_calls_is_the_one_the_policy_names():
    """Another provider of the web search is another recipient: this falls before the policy can go stale."""
    assert urlsplit(settings.ASSISTANT_SEARCH_URL).hostname.endswith(".brave.com")


@pytest.mark.django_db
def test_the_privacy_date_moved_with_the_last_change(client):
    """The version an account accepts is the date of the page (``accounts/tests/test_terms.py`` keeps them equal):
    a new default model provider is a new text, so both move, and every account accepts it at its next sign-in."""
    assert PRIVACY_VERSION > date(2026, 11, 17)
    assert "November 17, 2026" not in privacy(client, "en")
    assert "17 de noviembre de 2026" not in privacy(client, "es")


# The dictation of the account's panel reaches the same provider without a hub in the way.
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
# ``assistant/queries/usage.py`` ``monthly_limit``) bound the questions that reach the model. The account's panel on
# erplora.com has an assistant of its own, with the same chat and the same dictation.

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
    [model] = list_items_naming(html, "Anthropic Ireland, Limited")

    assert [promise for promise in expected["promises"] if promise in html] == []
    assert [condition for condition in expected["condition"] if condition not in html] == []
    assert expected["basis"] in model
