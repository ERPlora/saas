"""The cookie banner of every public page and the cookie settings page (``public/templates/cookie_consent/``)."""

import re

import pytest
from django.urls import reverse

from public.tests.template_pages import PUBLIC_STATIC, PUBLIC_TEMPLATES, get_page, region

pytestmark = pytest.mark.urls("public.tests.urls")


# --- The cookie banner and the cookie settings page -------------------------------------------


@pytest.mark.django_db
def test_the_cookie_banner_appears_until_a_choice_is_made(client, cookie_groups):
    assert 'id="cookie-consent-banner"' in get_page(client).content.decode()

    client.post(reverse("cookie_consent_accept"), {"all_groups": "on"})

    assert 'id="cookie-consent-banner"' not in get_page(client).content.decode()


@pytest.mark.django_db
def test_the_cookie_banner_uses_the_shared_container_and_compact_ionic_actions(
    client, cookie_groups
):
    html = get_page(client).content.decode()
    banner = region(html, 'id="cookie-consent-banner"', "</script>")
    banner_css = (PUBLIC_STATIC / "cookie-consent-banner.css").read_text(
        encoding="utf-8"
    )

    assert 'class="ep-container cookie-consent-layout"' in banner
    # Decline and Accept act on the page; Customize leads to another, so it is a real link.
    assert banner.count("<ion-button") == 2
    for control in ("cookie-customize", "cookie-decline", "cookie-accept"):
        assert f'id="{control}"' in banner
    assert re.search(r'<a id="cookie-customize" class="ep-button[^"]*" href="', banner)
    assert (
        "We use optional cookies to understand traffic and improve ERPlora." in banner
    )
    assert f'href="{reverse("cookie_consent_cookie_group_list")}"' in banner
    assert reverse("cookie_consent_accept") in banner
    assert reverse("cookie_consent_decline") in banner
    assert "X-CSRFToken" in banner
    for control in ("customize", "decline", "accept"):
        assert f"activateOnKeyboard({control}" in banner
    assert ".cookie-consent-actions ion-button" in banner_css
    assert ".cookie-consent-actions .ep-button" in banner_css
    assert "min-height: 2.75rem" in banner_css


@pytest.mark.django_db
def test_the_cookie_settings_page_lists_every_group_with_its_cookies(
    client, cookie_groups
):
    from cookie_consent.models import CookieGroup

    response = client.get(reverse("cookie_consent_cookie_group_list"))
    html = response.content.decode()

    assert response.status_code == 200
    assert '<nav class="ep-navbar"' in html
    assert "Cookie preferences" in html
    assert 'class="ep-container ep-section-content"' in html
    assert 'class="public-preference-list"' in html
    for group in CookieGroup.objects.all():
        assert group.name in html
        assert group.description in html
    # the required group is always active; the others have a toggle with their state
    assert "Always active" in html
    assert (
        html.count("<ion-toggle")
        == CookieGroup.objects.filter(is_required=False).count()
    )
    assert "data-cookie-state" in html
    assert 'class="ep-table-surface"' in html
    assert 'class="ep-table-stack"' in html
    assert 'data-title="Cookie name"' in html
    # the page is the decision centre: never the banner on top of it
    assert 'id="cookie-consent-banner"' not in html


@pytest.mark.django_db
def test_the_cookie_settings_page_says_so_when_there_are_no_groups(client):
    html = client.get(reverse("cookie_consent_cookie_group_list")).content.decode()

    assert "No cookie categories are currently configured." in html
    assert 'class="ep-inline-feedback' in html


@pytest.mark.django_db
def test_each_toggle_posts_its_group_to_accept_or_decline(client, cookie_groups):
    html = client.get(reverse("cookie_consent_cookie_group_list")).content.decode()
    script = next(
        script
        for script in re.findall(r"<script\b.*?</script>", html, re.S)
        if "ion-toggle.cookie-toggle" in script
    )

    assert reverse("cookie_consent_accept") in script
    assert reverse("cookie_consent_decline") in script
    assert "cookie_groups" in script
    assert "csrfmiddlewaretoken" in script
    assert 'data-group="analytical"' in html


def test_the_cookie_templates_keep_the_shared_patterns():
    page = (PUBLIC_TEMPLATES / "cookie_consent" / "cookiegroup_list.html").read_text(
        encoding="utf-8"
    )
    group = (PUBLIC_TEMPLATES / "cookie_consent" / "_cookie_group.html").read_text(
        encoding="utf-8"
    )
    public_css = (PUBLIC_STATIC / "public-landing.css").read_text(encoding="utf-8")

    assert 'include "public/partials/page_hero.html"' in page
    assert "{% block cookie_banner %}{% endblock %}" in page
    # Stored in English by init_cookie_groups, translated by the catalogue.
    assert "{% translate cookie_group.name as group_name %}" in group
    assert "{% translate cookie_group.description %}" in group
    assert "{% translate cookie.description %}{% else %}—{% endif %}" in group
    assert "data-title=\"{% trans 'Cookie name' %}\"" in group
    assert ".public-preference-list" in public_css
    assert "ion-toggle.cookie-toggle" in public_css
    assert "main ion-toggle:focus-visible" in public_css
