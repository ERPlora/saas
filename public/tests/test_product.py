"""``/features/``, ``/security/`` and ``/updates/`` (public/product.py).

Port of ``apps/public/product`` (origin/develop c5ca8ca): its only suite,
``product/tests/test_updates_page.py`` (10), and the cases of ``tests/unit/test_public_pages.py``
for these three pages (200, brand, the Features link of the navbar, the footer, GET only, the URL
names). What changed, and why:

* the URL names live in the ``public`` namespace (``public:features``…), not in ``product:``;
* the footer is ``<footer class="ep-footer">`` (L2), not ``<ok-footer>``: OutfitKit is gone;
* ``/updates/`` mirrors §7 of ``/legal/terms/``, which came with the pages that read ``Plan`` (L7);
  the CTA paints its button only when ``public:terms`` exists (``{% url … as %}``), so nothing ever
  pointed at a 404;
* «reachable from the footer» asks another public page, the footer being the same partial on all of
  them (``/`` was the launcher until the landing arrived, L7).
"""

import pytest
from django.conf import settings
from django.urls import NoReverseMatch, reverse

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
    assert "Built with modern technology." in html
    assert html.count('class="ep-feature-card"') == 2
    assert "Ready to get started?" in html
    assert f'href="{reverse("account_login")}"' in html


def test_features_does_not_advertise_the_retired_ui_stack(client):
    """OutfitKit is gone (PLAN §16.11): the stack card no longer names it."""
    assert "OutfitKit" not in page(client, "/features/")


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


def test_updates_page_links_the_contract_clause_once_it_exists_and_never_a_dead_link(
    client,
):
    """The band always says where the binding text is; its button appears with ``public:terms``
    (L7), never before: until then it would point at a 404."""
    html = page(client, "/updates/")

    assert "section 7 of the terms of service" in html
    try:
        terms = reverse("public:terms")
    except NoReverseMatch:
        assert "Read section 7" not in html
    else:
        assert "Read section 7" in html
        assert f'href="{terms}"' in html


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
#: The old hosting: Hetzner, in Falkenstein, Germany, behind Cloudflare (out: PLAN-AWS, ADR-0499).
OLD_HOSTING = ("hetzner", "falkenstein", "germany", "alemania", "cloudflare")


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", L3A_PAGES)
def test_no_page_names_the_old_hosting(client, path, language):
    text = page(client, path, language).lower()

    assert [name for name in OLD_HOSTING if name in text] == []


@pytest.mark.parametrize(
    ("language", "region"),
    [
        ("en", "Amazon Web Services, Spain region (eu-south-2, Aragón)"),
        ("es", "Amazon Web Services, región de España (eu-south-2, Aragón)"),
    ],
)
def test_security_names_the_aws_region_in_spain(client, language, region):
    assert region in page(client, "/security/", language)


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
# GitHub sign-in (Google only).

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
)


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("path", ["/security/", "/features/", "/about/"])
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
                "High availability on AWS, with daily backups",
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
                "Alta disponibilidad en AWS, con copias de seguridad diarias",
                "Límite de peticiones por IP y WAF",
            ),
        ),
    ],
)
def test_security_states_what_the_new_stack_does(client, language, claims):
    html = page(client, "/security/", language)

    assert [claim for claim in claims if claim not in html] == []
