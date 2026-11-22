"""``{% load prose %}``: the filters of a rendered text (``.ep-prose``, layout.css).

``scroll_tables`` puts every ``<table>`` of an HTML fragment inside its own
``div.ep-table-scroll``, the box that scrolls sideways when the table is wider than the text:
on a phone, a manual's table would otherwise be cut by the card around it. The table keeps its
full width when it fits, so a desktop sees no difference. Contract: public/tests/test_prose.py.
"""

import re

from django import template

register = template.Library()

#: A whole table, from its opening tag to its closing one; Markdown tables never nest.
TABLE = re.compile(r"<table(?=[\s>]).*?</table>", re.DOTALL)


@register.filter(is_safe=True)
def scroll_tables(html: str) -> str:
    """Each ``<table>…</table>`` → ``<div class="ep-table-scroll"><table>…</table></div>``; safe
    input stays safe, any other is still escaped."""
    return TABLE.sub(lambda table: f'<div class="ep-table-scroll">{table.group(0)}</div>', html)
