"""A button of the public web that leads somewhere is a real link: only ``public/components/button.html`` writes it,
through ``{% button %}``, so it works before the page script, compiles and has the style each page asks of it."""

import re
from pathlib import Path

import pytest
from django.template.loader import get_template

from public.tests.template_pages import COMPONENT_CSS, PUBLIC_TEMPLATES, public_templates, without_comments

pytestmark = pytest.mark.urls("public.tests.urls")


# --- A button that leads somewhere is a real link ------------------------------------------------

#: An ion-button with an href, over several lines and with template tags among its attributes.
ION_BUTTON_LINK = re.compile(r"<ion-button\b[^>]*(?<![\w-])href=")
#: Any element dressed as the shared link button, with its tag name.
BUTTON_LINK = re.compile(r"<([\w-]+)\b[^>]*\bclass=\"[^\"]*\bep-button\b[^\"]*\"[^>]*>")
#: A call of the button's tag. Django tags never span lines, so a call is one line of its template.
BUTTON_CALL = re.compile(r"\{%\s*button\b.*?%\}")


def ion_button_links(source: str) -> list[str]:
    return ION_BUTTON_LINK.findall(without_comments(source))


def button_calls(template: Path) -> list[str]:
    return BUTTON_CALL.findall(without_comments(template.read_text(encoding="utf-8")))


def test_no_button_of_the_public_web_waits_for_the_page_script_to_lead_anywhere():
    """An ion-button is no link until frontend/public.ts has defined it: pressed before that, on a slow connection
    or with the script blocked, nothing happens. Whatever leads to another page is an <a href> in the HTML."""
    offenders = [
        f"{template.relative_to(PUBLIC_TEMPLATES)}: {button}"
        for template in public_templates()
        for button in ion_button_links(template.read_text(encoding="utf-8"))
    ]

    assert offenders == []


@pytest.mark.parametrize(
    "tag",
    [
        '<ion-button href="/launch">',
        '<ion-button fill="outline" size="small" href="{% url \'public:app_download\' \'linux\' %}">',
        '<ion-button expand="block"{% if not plan.featured_label %} fill="outline"{% endif %} href="/launch">',
        '<ion-button\n  class="mt-auto"\n  href="/launch"\n>',
    ],
)
def test_the_button_sweep_catches_the_shapes_the_templates_had(tag):
    """Positive control: a sweep that finds nothing proves nothing."""
    assert ion_button_links(tag)


@pytest.mark.parametrize(
    "source",
    [
        '<ion-button type="submit">Send</ion-button>',
        '<ion-button id="cookie-accept" size="small">Accept</ion-button>',
        '<ion-button data-href="/launch">Not a link</ion-button>',
        '<a class="ep-button" href="/launch">Start free</a>',
        '{% comment %}<ion-button href="/launch">{% endcomment %}',
        '<ion-button type="submit"></ion-button> <a href="/launch">Start free</a>',
    ],
)
def test_the_button_sweep_leaves_alone_what_is_no_link_waiting_for_the_script(source):
    assert ion_button_links(source) == []


def test_every_link_button_really_is_a_link():
    """The shared class on anything but an <a href> would look like a button and lead nowhere."""
    offenders = [
        f"{template.relative_to(PUBLIC_TEMPLATES)}: {match.group(0)}"
        for template in public_templates()
        for match in BUTTON_LINK.finditer(without_comments(template.read_text(encoding="utf-8")))
        if match.group(1) != "a" or "href=" not in match.group(0)
    ]

    assert offenders == []


def test_only_the_button_component_writes_a_link_button():
    """One component: a button written by hand in a page is how the 50 of them would drift apart."""
    written = {
        str(template.relative_to(PUBLIC_TEMPLATES)): count
        for template in public_templates()
        if (count := len(BUTTON_LINK.findall(without_comments(template.read_text(encoding="utf-8")))))
    }

    assert written == {"public/components/button.html": 1}


def test_every_template_that_paints_a_button_compiles():
    """A missing ``{% load buttons %}`` or a misnamed argument takes the page down, and only some pages have a test."""
    templates = [template for template in public_templates() if button_calls(template)]

    assert templates
    for template in templates:
        get_template(str(template.relative_to(PUBLIC_TEMPLATES)))


def test_every_look_a_page_asks_of_a_button_has_its_style():
    """A modifier nobody wrote fails in silence: the button just looks wrong."""
    css = (COMPONENT_CSS / "button.css").read_text(encoding="utf-8")
    asked = {
        value
        for template in public_templates()
        for call in button_calls(template)
        for value in re.findall(r'\b(?:fill|size|color)="(\w+)"', call)
    }

    assert asked
    assert [name for name in sorted(asked - {"solid"}) if not re.search(rf"\.ep-button--{name}\b", css)] == []


@pytest.mark.parametrize(
    ("template", "full_width"),
    [
        ("appdist/android.html", 3),
        ("appdist/index.html", 3),
        ("demo/index.html", 3),
        ("downloads.html", 1),
        ("landing/home/_plan_cta.html", 1),
        ("pricing/_card_cta.html", 1),
    ],
)
def test_the_full_width_buttons_stay_full_width(template, full_width):
    """`expand="block"` of the ion-buttons these were: the cards' buttons fill the card."""
    calls = button_calls(PUBLIC_TEMPLATES / "public" / template)

    assert sum("block=True" in call for call in calls) == full_width
