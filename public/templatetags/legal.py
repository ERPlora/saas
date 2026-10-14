"""``{% load legal %}``: the filters of the legal pages (public/templates/public/legal/).

``demote_h1`` turns every ``<h1>`` of an HTML fragment into an ``<h2>``. The declaración
responsable is a Markdown deed whose ``# title`` renders as an ``<h1>``, and its page already has
one, the hero: two ``<h1>`` on one page (L8). The deed is published as it is (art. 13 RRSIF), so
its title is kept, one level down; ``demote_h1:"ep-deed-title"`` also gives it a class, so it keeps
the size of a page title (layout.css). Contract: public/tests/test_legal_tags.py.
"""

import re

from django import template

register = template.Library()

#: The opening and closing tags of an ``<h1>``, never a longer name that starts with it.
H1_TAG = re.compile(r"<(/?)h1(?=[\s>])", re.IGNORECASE)
#: The opening tag of an ``<h1>``, with its attributes.
H1_OPENING = re.compile(r"<h1(?=[\s>])([^>]*)>", re.IGNORECASE)
#: The start of a ``class`` attribute, with its quote.
CLASS_ATTRIBUTE = re.compile(r"\bclass=([\"'])", re.IGNORECASE)


def _with_class(opening: re.Match[str], css_class: str) -> str:
    attributes = opening.group(1)
    if CLASS_ATTRIBUTE.search(attributes):
        joined = CLASS_ATTRIBUTE.sub(rf"class=\g<1>{css_class} ", attributes, count=1)
        return f"<h1{joined}>"
    return f'<h1 class="{css_class}"{attributes}>'


@register.filter(is_safe=True)
def demote_h1(html: str, css_class: str = "") -> str:
    """``<h1 …>…</h1>`` → ``<h2 …>…</h2>``, with ``css_class`` added to its classes when given;
    safe input stays safe, any other is still escaped."""
    if css_class:
        html = H1_OPENING.sub(lambda opening: _with_class(opening, css_class), html)
    return H1_TAG.sub(r"<\1h2", html)
