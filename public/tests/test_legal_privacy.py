"""The privacy policy, ``/legal/privacy/``, and the processors the legal pages name: AWS hosts the data, in its
Ireland region, eu-west-1 (who handles the email is in ``test_privacy_mail_processor.py``; what the policy says of the
AI assistant, in ``test_legal_privacy_assistant.py``).
"""

import re

import pytest
from django.urls import reverse

from public.tests.conftest import without_tokens
from public.tests.legal_pages import PAGES, list_items_naming, spanish


# --- Privacy policy ----------------------------------------------------------------------------


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
    """GDPR art. 17 and 17(3)(b): the payer details and the Stripe customer go with the account;
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
    """We modify the system that processes our customer's customers' data, unilaterally.

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
def test_privacy_declares_the_llm_providers_actually_in_use(client):
    """Art. 13.1.e / 28.2 GDPR: the sub-processors that actually see the data are named, each with its role: the
    model that answers by default and the one in reserve."""
    html = spanish(client, "/legal/privacy/")
    [default] = list_items_naming(html, "Anthropic Ireland, Limited")
    [backup] = list_items_naming(html, "Model Studio")

    assert "POR DEFECTO" in default
    assert "RESPALDO" in backup and "Fráncfort" in backup


@pytest.mark.django_db
def test_privacy_states_assistant_data_does_not_reach_china(client):
    """China has no adequacy decision, so silence here reads as a Chapter V transfer."""
    html = spanish(client, "/legal/privacy/")

    assert "China" in html
    assert "no se transfieren" in html or "no salen" in html


@pytest.mark.django_db
def test_privacy_does_not_name_llm_providers_we_never_engaged(client):
    """Naming a processor we hold no credential for is a false disclosure, not a safe extra."""
    assert "DeepSeek" not in spanish(client, "/legal/privacy/")


#: The AI models by name: the policy names who processes the data, never the model, which changes.
AI_MODELS = ("Claude", "Haiku", "Sonnet", "Opus", "Qwen", "GPT", "Gemini", "Whisper", "whisper")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "outside_the_eea"),
    [("en", "outside the European Economic Area"), ("es", "fuera del Espacio Económico Europeo")],
)
def test_privacy_names_who_processes_the_ai_data_and_no_model(client, language, outside_the_eea):
    """Art. 13.1.e GDPR: the language model's processors by their entities; the default one never as processing in
    the EU, since it may route the queries outside the EEA."""
    html = client.get("/legal/privacy/").content.decode() if language == "en" else spanish(client, "/legal/privacy/")
    [default] = list_items_naming(html, "Anthropic Ireland, Limited")

    assert list_items_naming(html, "Alibaba (Netherlands) B.V.")
    assert outside_the_eea in default
    assert [model for model in AI_MODELS if re.search(rf"\b{model}\b", html)] == []


@pytest.mark.django_db
def test_privacy_describes_what_the_assistant_actually_sends_to_the_model(client):
    """No copy of the hub database, no stored conversation, only each query's result."""
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


# --- Where the data is hosted: on AWS, not on Hetzner --------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("path", PAGES.values())
@pytest.mark.parametrize(
    "provider",
    [
        "Hetzner",  # the old hosting, in Germany
        "Cloudflare",  # replaced by AWS WAF + ALB + Route 53
        # No voice of the server: reading aloud is the device's, and no text goes to Azure AI Speech.
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
    """Hosting, database, backups, storage and the network edge (DNS, DDoS protection) are AWS's, Ireland region
    ``eu-west-1``, since the ERP serves all of Europe: never the Spain region (``eu-south-2``, Aragón), and never as
    an inactive fallback. «España» stays in the page: it is the company's address, not where the data lives."""
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
def test_privacy_keeps_the_backup_model_in_frankfurt(client):
    """The backup language model stays in Alibaba Cloud's Frankfurt region."""
    [ai] = list_items_naming(
        client.get("/legal/privacy/").content.decode(), "Model Studio"
    )
    [ia] = list_items_naming(spanish(client, "/legal/privacy/"), "Model Studio")

    assert "Frankfurt" in ai
    assert "Fráncfort" in ia
