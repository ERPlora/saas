"""``{% load legal %}`` (public/templatetags/legal.py): the filters of the legal pages.

``demote_h1``: the declaración responsable is a Markdown deed whose ``# title`` renders as an
``<h1>``, and the page already has its own (the hero): two ``<h1>`` on one page (L8). The deed is
published as it is (art. 13 RRSIF), so its title is not dropped: it becomes an ``<h2>``.
"""

from django.template import Context, Template
from django.utils.safestring import mark_safe

from public.templatetags.legal import demote_h1


def test_the_title_of_the_deed_becomes_an_h2():
    html = "<h1>Declaración responsable — v2</h1><p>Texto</p><h2>1. Declarante</h2>"

    assert demote_h1(html) == (
        "<h2>Declaración responsable — v2</h2><p>Texto</p><h2>1. Declarante</h2>"
    )


def test_its_attributes_are_kept():
    assert demote_h1('<h1 id="title">T</h1>') == '<h2 id="title">T</h2>'


def test_every_h1_is_demoted_so_the_page_keeps_one():
    assert demote_h1("<h1>A</h1><h1>B</h1>") == "<h2>A</h2><h2>B</h2>"


def test_a_class_marks_the_demoted_title():
    """``demote_h1:"ep-deed-title"``: the deed's title keeps the size it had as a page title (L8)
    without being a second ``<h1>``; the other headings are left as they are."""
    html = "<h1>Declaración responsable — v2</h1><h2>1. Declarante</h2>"

    assert demote_h1(html, "ep-deed-title") == (
        '<h2 class="ep-deed-title">Declaración responsable — v2</h2><h2>1. Declarante</h2>'
    )


def test_the_class_joins_the_ones_the_title_already_has():
    assert demote_h1('<h1 id="t" class="lead">T</h1>', "ep-deed-title") == (
        '<h2 id="t" class="ep-deed-title lead">T</h2>'
    )


def test_html_without_an_h1_is_left_alone():
    html = "<h2>1. Declarante</h2><p>h1 is only text here</p><h10>no tag</h10>"

    assert demote_h1(html) == html


def test_safe_html_stays_safe_and_plain_text_is_still_escaped():
    """``is_safe``: the template engine keeps safe input safe and never turns a plain string into
    markup (the engine applies it, so it is asserted through a template, not a direct call)."""
    template = Template("{% load legal %}{{ html|demote_h1 }}")

    safe = template.render(Context({"html": mark_safe("<h1>T</h1>")}))
    unsafe = template.render(Context({"html": "<h1>T</h1>"}))

    assert safe == "<h2>T</h2>"
    assert unsafe == "&lt;h2&gt;T&lt;/h2&gt;"
