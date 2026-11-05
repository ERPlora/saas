"""``{% button %}``: the one link button of the public web (saas#238, PUBLIC-F11).

A button that leads to another page is an ``<a href>`` that works before the page's script has run. Its markup lives
in one place, ``public/components/button.html``, and each page asks for it in one line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template, TemplateSyntaxError
from django.urls import NoReverseMatch, reverse
from django.utils import translation

BUTTON_CSS = Path(settings.BASE_DIR) / "public" / "static" / "public" / "components" / "button.css"


def render(call: str, **context) -> str:
    return Template("{% load buttons %}" + call).render(Context(context)).strip()


def classes_of(html: str) -> list[str]:
    return re.search(r'class="([^"]*)"', html).group(1).split()


def test_a_button_is_a_link_with_the_shared_class_and_nothing_else():
    assert render('{% button href="/launch" label="Start free" %}') == (
        '<a class="ep-button" href="/launch">Start free</a>'
    )


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ('fill="solid"', []),
        ('fill="outline"', ["ep-button--outline"]),
        ('fill="clear"', ["ep-button--clear"]),
        ('size="small"', ["ep-button--small"]),
        ('size="large"', ["ep-button--large"]),
        ('color="light"', ["ep-button--light"]),
        ("block=True", ["ep-button--block"]),
        ("block=False", []),
        ('extra_class="mt-auto"', ["mt-auto"]),
        (
            'fill="outline" size="small" color="light" block=True extra_class="mt-auto"',
            ["ep-button--outline", "ep-button--small", "ep-button--light", "ep-button--block", "mt-auto"],
        ),
    ],
)
def test_each_look_is_a_modifier_of_the_shared_class(arguments, expected):
    html = render('{% button href="/launch" label="Go" ' + arguments + " %}")

    assert classes_of(html) == ["ep-button", *expected]


def test_a_look_chosen_by_the_page_at_render_time():
    call = '{% button href="/launch" label="Go" fill=plan.featured|yesno:"solid,outline" %}'

    assert classes_of(render(call, plan={"featured": True})) == ["ep-button"]
    assert classes_of(render(call, plan={"featured": False})) == ["ep-button", "ep-button--outline"]


def test_every_look_of_the_component_has_its_style():
    """A modifier nobody wrote fails in silence: the button just looks wrong."""
    css = BUTTON_CSS.read_text(encoding="utf-8")

    for name in ("outline", "clear", "small", "large", "light", "block"):
        assert re.search(rf"\.ep-button--{name}\b", css), name
    for name in ("start", "end"):
        assert re.search(rf"\.ep-button__{name}\b", css), name


def href_of(html: str) -> str:
    return re.search(r'href="([^"]*)"', html).group(1)


def test_the_address_can_be_the_name_of_a_url():
    assert href_of(render('{% button href="public:demo" label="Go" %}')) == reverse("public:demo")


def test_the_name_of_a_url_takes_its_argument():
    html = render('{% button href="public:app_download" arg="linux" label="Go" %}')

    assert href_of(html) == reverse("public:app_download", args=["linux"])


def test_the_address_takes_a_query():
    html = render('{% button href="public:contact" query="subject=security" label="Go" %}')

    assert href_of(html) == f"{reverse('public:contact')}?subject=security"


def test_a_literal_query_on_a_path():
    assert href_of(render('{% button href="/launch" query="a=1" label="Go" %}')) == "/launch?a=1"


def test_the_address_can_be_a_variable_and_is_escaped():
    url = "https://demo.erplora.com/start/?code=1&next=/"

    assert href_of(render('{% button href=url label="Go" %}', url=url)) == (
        "https://demo.erplora.com/start/?code=1&amp;next=/"
    )


def test_the_address_can_be_a_mail_built_by_the_page():
    call = '{% button href="mailto:"|add:email|add:"?subject=Collaborator%20Program" label="Go" %}'

    assert href_of(render(call, email="support@erplora.com")) == (
        "mailto:support@erplora.com?subject=Collaborator%20Program"
    )


def test_a_url_name_that_does_not_exist_is_a_clear_error_not_a_dead_link():
    with pytest.raises(NoReverseMatch):
        render('{% button href="public:no_such_page" label="Go" %}')


def test_a_label_from_a_variable_is_escaped():
    assert ">&lt;b&gt;Go&lt;/b&gt;</a>" in render('{% button href="/launch" label=text %}', text="<b>Go</b>")


def test_a_label_is_translated_where_the_page_marks_it():
    call = '{% button href="/launch" label=_("Start free") %}'

    with translation.override("es"):
        spanish = render(call)
    with translation.override("en"):
        english = render(call)

    assert ">Start free</a>" in english
    assert "Start free" not in spanish and spanish.endswith("</a>")


def test_an_icon_goes_before_the_label():
    html = render('{% button href="/launch" label="Go" start_icon="lucide:arrow-right" %}')

    assert re.fullmatch(
        r'<a class="ep-button" href="/launch"><span class="ep-button__start"><svg [^>]*>.*</svg></span>Go</a>',
        html,
        re.S,
    )


def test_an_icon_goes_after_the_label():
    html = render('{% button href="/launch" label="Go" end_icon="lucide:arrow-right" %}')

    assert re.fullmatch(
        r'<a class="ep-button" href="/launch">Go<span class="ep-button__end"><svg [^>]*>.*</svg></span></a>',
        html,
        re.S,
    )


@pytest.mark.parametrize("position", ["start_icon", "end_icon"])
def test_an_icon_takes_its_size_and_otherwise_follows_the_text(position):
    sized = render('{% button href="/launch" label="Go" ' + position + '="lucide:arrow-right" icon_size=15 %}')
    free = render('{% button href="/launch" label="Go" ' + position + '="lucide:arrow-right" %}')

    assert 'width="15" height="15"' in sized
    assert 'width="1em" height="1em"' in free


def test_the_label_can_carry_its_own_class():
    html = render('{% button href="/launch" label="Windows" start_icon="lucide:arrow-right" label_class="ml-1" %}')

    assert html.endswith('</span><span class="ml-1">Windows</span></a>')


def test_a_button_a_script_or_a_test_finds_keeps_its_attributes():
    html = render('{% button href="/launch" label="Go" id="cookie-customize" testid="demo-retry" %}')

    assert html == '<a id="cookie-customize" class="ep-button" href="/launch" data-testid="demo-retry">Go</a>'


@pytest.mark.parametrize(
    "call",
    [
        '{% button label="Go" %}',
        '{% button href="/launch" %}',
        '{% button href="/launch" label="Go" sise="large" %}',
        '{% button "/launch" "Go" %}',
    ],
)
def test_a_call_that_is_wrong_does_not_compile(call):
    """A typo in an argument is an error when the template loads, never a button that quietly looks wrong."""
    with pytest.raises(TemplateSyntaxError):
        render(call)
