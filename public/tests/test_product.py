"""``/features/``, ``/security/`` and ``/updates/`` (public/product.py).

Port of ``apps/public/product`` (origin/develop c5ca8ca): its only suite,
``product/tests/test_updates_page.py`` (10), and the cases of ``tests/unit/test_public_pages.py``
for these three pages (200, brand, the Features link of the navbar, the footer, GET only, the URL
names). What changed, and why:

* the URL names live in the ``public`` namespace (``public:features``…), not in ``product:``;
* the footer is ``<footer class="ep-footer">`` (L2), not ``<ok-footer>``: OutfitKit is gone;
* ``/updates/`` mirrors §7 of ``/legal/terms/``, which came with the pages that read ``Plan`` (L7),
  and its closing band links it;
* «reachable from the footer» asks another public page, the footer being the same partial on all of
  them (``/`` was the launcher until the landing arrived, L7).
"""

import re

import pytest
from django.conf import settings
from django.urls import reverse

from public.tests.test_stack_copy import copy_of, names_the_stack

pytestmark = pytest.mark.django_db

PAGES = ("/features/", "/security/", "/updates/")


def page(client, path: str, language: str = "en") -> str:
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response.content.decode()


# --- The three pages (tests/unit/test_public_pages.py) ------------------------------------------


@pytest.mark.parametrize("path", PAGES)
def test_the_page_answers_with_the_brand_the_navbar_and_the_footer(client, path):
    html = page(client, path)

    assert "ERPlora" in html
    assert '<nav class="ep-navbar"' in html
    assert f'href="{reverse("public:features")}"' in html
    assert '<footer class="ep-footer"' in html


@pytest.mark.parametrize("path", PAGES)
def test_the_page_only_answers_safe_methods(client, path):
    assert client.post(path).status_code == 405


def test_the_url_names():
    assert reverse("public:features") == "/features/"
    assert reverse("public:security") == "/security/"
    assert reverse("public:updates") == "/updates/"


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("/features/", "<title>Features · ERPlora</title>"),
        ("/security/", "<title>Security · ERPlora</title>"),
        ("/updates/", "<title>Updates · ERPlora</title>"),
    ],
)
def test_each_page_has_its_own_title(client, path, title):
    assert title in page(client, path)


# --- /features/ ------------------------------------------------------------------------------


def test_features_keeps_its_sections(client):
    html = page(client, "/features/")

    assert "Powerful features for modern businesses." in html
    assert html.count('class="ep-bento-item ') == 5
    assert "Ready to get started?" in html
    assert 'href="/launch"' in html
    assert "/accounts/login/" not in html


@pytest.mark.parametrize(
    ("language", "section"),
    [
        ("en", "Built with modern technology"),
        ("es", "Construido con tecnología moderna"),
    ],
)
def test_features_does_not_name_the_stack(client, language, section):
    """Ioan, 2026-10-14: the page says what ERPlora does, not what it is built with. The «Built with
    modern technology.» section and its two stack cards are gone, and so are the names the bento and
    the meta descriptions dropped in passing (OutfitKit had already left, PLAN §16.11)."""
    html = copy_of(page(client, "/features/", language))

    assert section not in html
    assert 'class="ep-feature-card"' not in html
    assert names_the_stack(html) == []
    assert "OutfitKit" not in html


@pytest.mark.parametrize(
    ("language", "sentences"),
    [
        (
            "en",
            (
                "Always available",
                "Process transactions in milliseconds, with live updates on every device.",
                "lightning-fast POS, modular architecture, continuous backups,",
            ),
        ),
        (
            "es",
            (
                "Siempre disponible",
                "Procesa transacciones en milisegundos, con actualizaciones en vivo en todos los "
                "dispositivos.",
                "POS ultrarrápido, arquitectura modular, copias de seguridad continuas,",
            ),
        ),
    ],
)
def test_features_says_what_the_platform_gives_instead(client, language, sentences):
    html = page(client, "/features/", language)

    for sentence in sentences:
        assert sentence in html, sentence


def test_features_in_spanish(client):
    html = page(client, "/features/", "es")

    assert "Funciones potentes para negocios modernos." in html
    assert "¿Listo para comenzar?" in html


# --- /security/ ------------------------------------------------------------------------------


def test_security_keeps_its_four_cards_and_the_contact_band(client):
    html = page(client, "/security/")

    assert "Enterprise-grade security." in html
    assert html.count('class="ep-feature-card"') == 4
    for heading in (
        "Authentication & Authorization",
        "Data Protection",
        "Infrastructure Security",
        "Compliance",
    ):
        assert heading in html
    assert "Talk to our security team." in html
    # The contact page comes with the landing (L7), at the address it has today.
    assert 'href="/contact/"' in html


def test_security_in_spanish(client):
    assert "Seguridad de nivel empresarial." in page(client, "/security/", "es")


# --- /updates/ (product/tests/test_updates_page.py) --------------------------------------------


def test_updates_page_is_no_longer_a_coming_soon_stub(client):
    """It shipped as a placeholder; a placeholder cannot carry a policy."""
    html = page(client, "/updates/")

    assert "coming soon" not in html.lower()
    assert "noindex" not in html


def test_updates_page_explains_why_we_do_not_ask(client):
    html = page(client, "/updates/", "es")

    assert "No te preguntamos" in html
    assert "lo hacemos nosotros" in html


def test_updates_page_states_the_four_commitments(client):
    """Same four obligations as clause 7, in words a shop owner reads once and keeps."""
    html = page(client, "/updates/", "es")

    assert "No para tu trabajo" in html
    assert "No te quita nada" in html
    assert "Si sale mal, vuelve atrás" in html
    assert "Puedes ver qué cambió" in html


def test_updates_page_states_when_we_do_warn(client):
    """The login → charge path is the one thing an update is not allowed to move silently."""
    html = page(client, "/updates/", "es")

    assert "iniciar sesión" in html
    assert "cobrar" in html


def test_updates_page_says_you_can_bring_an_update_forward(client):
    """You cannot postpone it, but the Update button is still there (ADR-0269 §3.5)."""
    assert "Puedes adelantarlo" in page(client, "/updates/", "es")


def test_updates_page_carves_out_the_installable_app(client):
    assert "nunca la instalamos por ti" in page(client, "/updates/", "es")


def test_updates_page_tells_you_that_you_can_walk_away(client):
    """The terms give a 30-day right to terminate free of charge when a change hurts you."""
    html = page(client, "/updates/", "es")

    assert "treinta días" in html
    assert "sin pagar nada" in html
    assert "la parte que no hayas usado" in html


def test_updates_page_links_the_contract_clause(client):
    """A plain-language page that does not point at the binding text is marketing, not a policy."""
    assert "/legal/terms/" in page(client, "/updates/", "es")


def test_updates_page_closing_band_links_the_contract_clause(client):
    """The band says where the binding text is and links it (``public:terms``, L7)."""
    html = page(client, "/updates/")

    assert "section 7 of the terms of service" in html
    # The button itself, not the footer's «Terms», which links the same page from every page.
    assert f'href="{reverse("public:terms")}">Read section 7</ion-button>' in html


def test_updates_page_is_reachable_from_the_footer(client):
    """An unlinked page explains nothing to anybody."""
    assert 'href="/updates/"' in page(client, "/features/")


# --- Navigation, sitemap and llms.txt ---------------------------------------------------------


def footer_of(html: str) -> str:
    return html[html.index('<footer class="ep-footer"') :]


def test_the_navbar_links_features(client):
    html = page(client, "/security/")
    navbar = html[html.index('<nav class="ep-navbar"') : html.index("</nav>")]

    assert f'href="{reverse("public:features")}">Features</a>' in navbar


def test_the_footer_links_the_three_product_pages_in_the_old_order(client):
    footer = footer_of(page(client, "/about/"))
    positions = [
        footer.index(f'href="{reverse(name)}"')
        for name in ("public:features", "public:security", "public:updates")
    ]

    assert positions == sorted(positions)


def test_the_sitemap_lists_the_product_pages_with_their_priorities():
    from public.sitemaps import StaticPagesSitemap

    for entry in (
        ("public:features", 0.8),
        ("public:security", 0.7),
        ("public:updates", 0.5),
    ):
        assert entry in StaticPagesSitemap.pages


def test_llms_txt_points_answer_engines_at_features_and_security(client):
    body = client.get("/llms.txt").content.decode()

    assert (
        "- [Features](https://testserver/features/): what the platform does across ERP, "
        "POS and back office." in body
    )
    assert (
        "- [Security](https://testserver/security/): how customer data is isolated and "
        "protected." in body
    )


# --- Where it is hosted (Ioan, 2026-10-13: the servers are on AWS, not on Hetzner) ---------------

#: Every page of this lot, product, company, resources, help and the app.
L3A_PAGES = (
    "/features/",
    "/security/",
    "/updates/",
    "/about/",
    "/blog/",
    "/careers/",
    "/press/",
    "/documentation/",
    "/support/",
    "/help/",
    "/app/",
    "/download/",
)
#: The old hosting: Hetzner, in Falkenstein, Germany, behind Cloudflare (out: PLAN-AWS, ADR-0499),
#: and the AWS Spain region the pages named until Ireland took its place (Ioan, 2026-10-14).
OLD_HOSTING = (
    "hetzner",
    "falkenstein",
    "germany",
    "alemania",
    "cloudflare",
    "eu-south-2",
    "aragón",
)


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", L3A_PAGES)
def test_no_page_names_the_old_hosting(client, path, language):
    text = page(client, path, language).lower()

    assert [name for name in OLD_HOSTING if name in text] == []


@pytest.mark.parametrize(
    ("language", "region"),
    [
        ("en", "Amazon Web Services, Ireland region (eu-west-1)"),
        ("es", "Amazon Web Services, región de Irlanda (eu-west-1)"),
    ],
)
def test_security_names_the_aws_region_in_ireland(client, language, region):
    """Ioan, 2026-10-14: Ireland, for all of Europe; never the Spain region named before."""
    html = page(client, "/security/", language)

    assert region in html
    assert "Spain region" not in html
    assert "región de España" not in html


@pytest.mark.parametrize(
    ("language", "perimeter"),
    [
        ("en", "DDoS protection and WAF on AWS"),
        ("es", "Protección anti-DDoS y WAF en AWS"),
    ],
)
def test_security_names_the_perimeter_on_aws(client, language, perimeter):
    """Route 53, AWS WAF and the ALB are the perimeter (ADR-0499); no CDN in front."""
    html = page(client, "/security/", language)

    assert perimeter in html
    assert "CDN" not in html


# --- Only what the new stack does (Ioan, 2026-10-13) ------------------------------------------
# The old copy promised RS256 JWT (PLAN-SAAS §2: server sessions and a one-time code to enter the
# hub), reCAPTCHA (there is none: the old CSP test fixed it), a 99.95 % SLA (the pricing tests
# fixed «no uptime SLA»), Cloudflare (out, ADR-0499), Argon2 (saas-next keeps Django's PBKDF2),
# required email verification (`ACCOUNT_EMAIL_VERIFICATION = "none"`), 2FA (off in phase 1) and
# GitHub sign-in (Google only). The home and /contact/ promised the same SLA as an «Uptime 99.95%»
# and support «24/7» (L8): the real promise is high availability on AWS and a reply within 4
# business hours, the one of the contact form.

STALE_CLAIMS = (
    "Cloudflare",
    "JWT",
    "reCAPTCHA",
    "99.95",
    "99,95",
    "Argon2",
    "GitHub",
    "2FA",
    "End-to-end",
    "extremo a extremo",
    "Email verification required",
    "email verification",
    "24/7",
    "Uptime",
    "uptime",
    "Tiempo activo",
    "Tiempo Activo",
    "tiempo activo",
    # The catalogue sells apps, not modules (decision 19; L8 found them left on these pages).
    "modules",
    "Modules",
    "módulos",
    "Módulos",
)


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(
    "path",
    [
        "/security/",
        "/features/",
        "/about/",
        "/",
        "/contact/",
        "/collaborate/",
        "/help/",
        "/support/",
    ],
)
def test_no_page_promises_what_the_old_stack_did(client, path, language):
    html = page(client, path, language)

    assert [claim for claim in STALE_CLAIMS if claim in html] == []


@pytest.mark.parametrize(
    ("language", "claims"),
    [
        (
            "en",
            (
                "Server-side sessions in secure cookies (Secure, HttpOnly, SameSite)",
                "One-time code to enter your hub",
                "Sign in with Google",
                "Salted password hashing (PBKDF2)",
                "Encryption in transit and at rest",
                "DDoS protection and WAF on AWS",
                "High availability on AWS",
                "Continuous backups, point-in-time recovery for 14 days",
                "Rate limiting per IP and WAF",
            ),
        ),
        (
            "es",
            (
                "Sesiones de servidor en cookies seguras (Secure, HttpOnly, SameSite)",
                "Código de un solo uso para entrar en tu hub",
                "Inicio de sesión con Google",
                "Contraseñas guardadas con hash y sal (PBKDF2)",
                "Cifrado en tránsito y en reposo",
                "Protección anti-DDoS y WAF en AWS",
                "Alta disponibilidad en AWS",
                "Copias de seguridad continuas, recuperación a cualquier momento de los últimos 14 días",
                "Límite de peticiones por IP y WAF",
            ),
        ),
    ],
)
def test_security_states_what_the_new_stack_does(client, language, claims):
    html = page(client, "/security/", language)

    assert [claim for claim in claims if claim not in html] == []


# --- PUBLIC-F07: the web promises only what the product does today (SAAS_PUBLIC-F76) --------------
# Checked against the apps of the Hub (origin/main): there is no accounting, payroll or support-ticket
# app, no TicketBAI and no tax returns (303, 390, 347), no warehouses, lots or expiry dates in
# inventory and no bank reconciliation; the release number was typed by hand. The competitors' own
# columns («Accounting + light CRM» of Holded) may still name what THEY do.

UNSHIPPED_CLAIMS = (
    "v3.4",
    "TicketBAI",
    "303·390·347",
    "bank reconciliation",
    "conciliación bancaria",
    "multi-warehouse",
    "multi-almacén",
    "lot/expiry",
    "lote/caducidad",
    "HR and payroll",
    "RRHH y nóminas",
    "Support tickets",
    "Tickets de soporte",
    "QuickBooks",
    "Zendesk",
    "Invoicing + accounting",
    "Facturación + contabilidad",
    "HR, accounting",
    "RRHH, contabilidad",
    "Accounting + POS",
    "Contabilidad + TPV",
    "POS + accounting",
    "TPV + contabilidad",
    "POS, accounting",
    "TPV, contabilidad",
    "Inventory + warehouse",
    "Inventario + almacén",
    "No limit",
    "Sin límite",
    "Reports + audit",
    "Informes + auditoría",
)


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize(
    "path", ["/", "/pricing/", "/features/", "/security/", "/about/", "/collaborate/"]
)
def test_no_page_promises_what_the_product_does_not_do(client, path, language):
    html = page(client, path, language)

    assert [claim for claim in UNSHIPPED_CLAIMS if claim in html] == []


@pytest.mark.parametrize(
    ("language", "sectors"),
    [("en", ("Healthcare", "Automotive", "Logistics")), ("es", ("Salud", "Automoción", "Logística"))],
)
def test_the_home_names_the_businesses_it_is_built_for_not_every_sector(client, language, sectors):
    """The trust strip said «Built for every kind of business» over sectors no vertical serves."""
    html = page(client, "/", language)
    strip = html[html.index('class="ep-logo-cloud') : html.index("</section>", html.index('class="ep-logo-cloud'))]

    assert [sector for sector in sectors if sector in strip] == []
    assert "every kind of business" not in strip
    assert "todo tipo de negocio" not in strip


STACK_ROW = re.compile(
    r'<tr><td data-title="[^"]+">([^<]+)</td><td data-title="[^"]+">[^<]+</td>'
    r'<td data-title="[^"]+" class="font-mono">€(\d+)</td>'
)
STACK_TOTAL = re.compile(r'<td colspan="2">[^<]+</td>\s*<td data-title="[^"]+" class="font-mono">€(\d+)</td>')


def test_the_typical_stack_total_is_the_sum_of_its_rows(client):
    """«€533» was typed next to rows that changed: the total is worked out from them."""
    html = page(client, "/")

    rows = STACK_ROW.findall(html)
    (total,) = STACK_TOTAL.findall(html)

    assert rows, "no row in the stack table"
    assert int(total) == sum(int(cost) for _, cost in rows)


# --- PUBLIC-F08: what the web says of security and data is what runs (SAAS_PUBLIC-F77) -------------
# The load balancer accepts TLS 1.2 and 1.3 (``ELBSecurityPolicy-TLS13-1-2-2021-06`` in ERPlora/aws):
# «TLS 1.3 required» was false. Nothing in the platform runs «regular security audits» nor has a
# pentest report to hand out. The privacy policy (§6) lets the assistant's backup model providers
# process outside the EEA: «your data never leaves the EU» contradicted it.

UNVERIFIED_SECURITY_CLAIMS = (
    "TLS 1.3 required",
    "TLS 1.3 requerido",
    "security audits",
    "Auditorías de seguridad",
    "pentest",
    "never leaves the EU",
    "nunca salen de la UE",
)


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", ["/security/", "/features/", "/pricing/", "/", "/about/"])
def test_no_page_claims_what_nobody_checked(client, path, language):
    html = page(client, path, language)

    assert [claim for claim in UNVERIFIED_SECURITY_CLAIMS if claim in html] == []


@pytest.mark.parametrize(
    ("language", "claim"),
    [("en", "HTTPS only, with TLS 1.2 or 1.3"), ("es", "Solo HTTPS, con TLS 1.2 o 1.3")],
)
def test_security_states_the_tls_versions_the_load_balancer_accepts(client, language, claim):
    assert claim in page(client, "/security/", language)


@pytest.mark.parametrize(
    ("language", "exception"),
    [
        ("en", "if its European provider is unavailable"),
        ("es", "si su proveedor europeo no está disponible"),
    ],
)
def test_the_storage_answer_names_the_one_exception_of_the_privacy_policy(client, language, exception):
    html = page(client, "/pricing/", language)
    answers = re.findall(r'<div class="ion-padding" slot="content">(.*?)</div>', html, re.S)
    (storage,) = [answer for answer in answers if "eu-west-1" in answer]

    assert exception in storage
    assert 'href="/legal/privacy/"' in storage
