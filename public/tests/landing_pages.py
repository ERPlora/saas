"""What the tests of the home ``/``, the contact page ``/contact/`` and its form ``/contact/submit/``
(public/landing.py) share: the plans they create, the page they read, the pieces of it they look at and the message
they post.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.messages import get_messages

from hubs.models import Plan

HOME = "/"
CONTACT = "/contact/"
SUBMIT = "/contact/submit/"


def make_plan(slug: str, *, trial_days: int = 0, **fields) -> Plan:
    defaults = {
        "name_en": slug.replace("-", " ").title(),
        "description_en": f"{slug} plan",
        "price_monthly": Decimal("29.99"),
        "trial_period_days": trial_days,
        "features_en": ["Unlimited users"],
        "features_es": ["Usuarios ilimitados"],
        "is_active": True,
    }
    return Plan.objects.create(slug=slug, **{**defaults, **fields})


def page(client, path: str = HOME, language: str | None = None):
    if language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(path)
    assert response.status_code == 200, path
    return response


def html_of(client, path: str = HOME, language: str | None = None) -> str:
    return page(client, path, language).content.decode()


def section(html: str, section_id: str) -> str:
    start = html.index(f'id="{section_id}"')
    return html[start : html.index("</section>", start)]


def hero(html: str) -> str:
    start = html.index('class="hero-bg')
    return html[start : html.index("</section>", start)]


VALID = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+34 600 000 000",
    "message": "Hello, I would like more information about ERPlora.",
}


def submit(client, **overrides):
    return client.post(SUBMIT, {**VALID, **overrides})


def messages_of(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def form_of(html: str) -> str:
    start = html.index('<form id="contact-form"')
    return html[start : html.index("</form>", start)]
