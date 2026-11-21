"""The terms of use, ``/legal/terms/``: they read ``Plan``."""

import re
from datetime import date

import pytest
from django.conf import settings
from django.urls import reverse

from accounts.models import TERMS_VERSION
from hubs.tests.test_plan_catalogue import APP_ON_A_CUSTOM_DOMAIN, CUSTOM_DOMAIN_WORDS
from public.tests.conftest import without_tokens
from public.tests.legal_pages import list_items_naming, paragraphs_of, section


# --- The Terms of Use ----------------------------------------------------------------------------
#
# * The trial of section 4 is read from the plans on sale through hubs.plan.list; the tests still create the rows with
#   the ORM of hubs.
# * The suspension clock of section 3 is public.legal.SUSPENDED_HUB_DELETE_DAYS: the task that deletes a suspended hub
#   lives in the Hub, so the number the terms print is pinned here.
# * Where ERPlora sells its paid plans (the clause with id=where-we-sell) is public/tests/test_where_we_sell.py.

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
    """Section 4 of the terms, so a «15 days» elsewhere on the page cannot make a test pass."""
    match = re.search(r"<h2>\s*4\..*?<h2>\s*5\.", terms_html(client, language), re.S)
    assert match, "the terms lost the headings of their sections 4 and 5"
    return match.group(0)


def trial_clause(section: str) -> str:
    return section.split("<li>", 1)[1].split("</li>", 1)[0]


# The clauses


#: What section 4(c) of Brave's terms asks each end user to agree to: obligations substantially like those of its
#: section 3(b).
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
    """Section 4(c) of Brave's terms: each end user is bound in writing to something like its section 3(b);
    acceptable use is where breach means suspension, as section 4(c) also asks."""
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


#: What the terms say of the custom domain: on the plans that include one, read from their rows, and only the public
#: website; the app and the way in stay on erplora.com.
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
    """Section 1 names the customer's own domains only on the plans whose ``includes_custom_domain`` is true, and
    only for the public website."""
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
    """No plan on sale with a custom domain, no custom domain in the terms."""
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


# The exit package


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
@pytest.mark.parametrize(
    ("language", "fragments"),
    [
        (
            "en",
            (
                "{days} days after a Hub is deleted, ERPlora erases its database and its files.",
                "Its sales, invoices and other fiscal documents are the exception: ERPlora keeps them for the 6 years "
                "the law requires them to be kept, in an archive that nobody, ERPlora included, can change or delete.",
                "That archive does not replace the copy the customer must keep, as described above.",
            ),
        ),
        (
            "es",
            (
                "A los {days} días de eliminarse un Hub, ERPlora borra su base de datos y sus ficheros.",
                "Sus ventas, facturas y demás documentos fiscales son la excepción: ERPlora los guarda durante los 6 "
                "años que la ley obliga a conservarlos, en un archivo que nadie, tampoco ERPlora, puede modificar ni "
                "borrar.",
                "Ese archivo no sustituye a la copia que el cliente debe conservar, como se indica arriba.",
            ),
        ),
    ],
)
def test_the_terms_say_what_is_kept_after_a_hub_is_erased_for_how_long_and_why(client, language, fragments):
    """The Hub erases a deleted business's database and files when its days to recover it end, all but its fiscal
    documents, which it keeps 6 years in the fiscal archive (BASE-F109): the terms say both, with the days read from
    the business's own clock."""
    from hubs.models import Hub

    paragraphs = paragraphs_of(section(terms_html(client, language), 5))
    erased = [paragraph for paragraph in paragraphs if fragments[0].format(days=Hub.RETENTION.days) in paragraph]

    assert len(erased) == 1
    for fragment in fragments[1:]:
        assert fragment in erased[0]


@pytest.mark.django_db
def test_a_spanish_customer_reads_the_exit_package_in_spanish(client, settings):
    html = terms_html(client, "es")

    assert str(settings.HUB_EXIT_PACKAGE_TTL_DAYS) in html
    assert "no se puede recuperar" in html.lower()
    assert "Código de Comercio" in html


# The trial period


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


# The date of the terms


@pytest.mark.django_db
def test_the_terms_date_moved_with_the_last_change(client):
    """The page says when its text last changed: every change of a clause moves the date, so no earlier date of the
    terms is still shown."""
    html = terms_html(client)
    spanish = terms_html(client, "es")

    for old in ("August 8, 2026", "October 1, 2026", "October 13, 2026", "October 25, 2026", "November 3, 2026",
                "November 5, 2026", "November 14, 2026"):
        assert old not in html, old
    assert TERMS_VERSION > date(2026, 11, 14)
    for old in ("25 de octubre de 2026", "3 de noviembre de 2026", "5 de noviembre de 2026", "14 de noviembre de 2026"):
        assert old not in spanish, old


# Our apps, not a marketplace, and all of them on every plan


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
    """Section 1 says every plan includes all the apps, with no «premium» tier anywhere in the terms."""
    tokens_spelling("premium")
    html = without_tokens(terms_html(client, language))

    assert clause in html
    assert "premium" not in html.lower()
