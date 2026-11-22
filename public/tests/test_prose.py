"""``{% load prose %}`` (public/templatetags/prose.py): the filters of a rendered text.

``scroll_tables``: a table wider than the text, such as an app manual's on a phone, scrolls
sideways inside its own box instead of being cut by the card around the text.
"""

from django.template import Context, Template
from django.utils.safestring import mark_safe

from public.templatetags.prose import scroll_tables

TABLE = "<table><thead><tr><th>Permiso</th></tr></thead><tbody><tr><td>Ver</td></tr></tbody></table>"


def test_a_table_goes_inside_its_own_scroll_box():
    html = f"<p>Antes</p>{TABLE}<p>Después</p>"

    assert scroll_tables(html) == (
        f'<p>Antes</p><div class="ep-table-scroll">{TABLE}</div><p>Después</p>'
    )


def test_every_table_gets_its_own_box():
    assert scroll_tables(f"{TABLE}<h2>Otra</h2>{TABLE}") == (
        f'<div class="ep-table-scroll">{TABLE}</div><h2>Otra</h2>'
        f'<div class="ep-table-scroll">{TABLE}</div>'
    )


def test_a_table_split_over_lines_is_boxed_whole():
    html = "<table>\n<tr>\n<td>Ver</td>\n</tr>\n</table>"

    assert scroll_tables(html) == f'<div class="ep-table-scroll">{html}</div>'


def test_html_without_a_table_is_left_alone():
    html = "<p>A table is only a word here</p>"

    assert scroll_tables(html) == html


def test_a_tag_whose_name_starts_like_table_is_not_a_table():
    assert scroll_tables(f"<tablet>no tag</tablet>{TABLE}") == (
        f'<tablet>no tag</tablet><div class="ep-table-scroll">{TABLE}</div>'
    )


def test_safe_html_stays_safe_and_plain_text_is_still_escaped():
    """``is_safe``: the template engine keeps safe input safe and never turns a plain string into
    markup (the engine applies it, so it is asserted through a template, not a direct call)."""
    template = Template("{% load prose %}{{ html|scroll_tables }}")

    safe = template.render(Context({"html": mark_safe(TABLE)}))
    unsafe = template.render(Context({"html": TABLE}))

    assert safe == f'<div class="ep-table-scroll">{TABLE}</div>'
    assert "<table>" not in unsafe
    assert "&lt;table&gt;" in unsafe
