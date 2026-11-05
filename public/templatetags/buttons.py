"""``{% button %}``: the one link button of the public web (saas#238, PUBLIC-F11).

A button that leads to another page, in one line of its page::

    {% load buttons %}
    {% button href="/launch" label=_("Start free") end_icon="lucide:arrow-right" %}
    {% button href="public:contact" query="subject=security" label=_("Contact us") fill="outline" size="large" %}
    {% button href="public:app_download" arg="linux" label=_("Download") block=True extra_class="mt-auto" %}

It paints an ``<a href>``, so it leads on before the page's script has run, without it, and with a middle click. What
does not navigate (a form's submit, Accept, Decline) stays an ``ion-button``. The look is ``components/button.css``.

``href`` is what ``django.shortcuts.redirect`` takes: the name of a URL, a path or a whole address (``arg`` is the
URL's argument, ``query`` what goes after the ``?``). A name that does not exist raises, it never paints a dead link.

Keyword-only on purpose: a misnamed argument is a ``TemplateSyntaxError`` when the template loads, never a button that
quietly looks wrong. ``start_icon`` and ``end_icon`` must be read by ``scripts/gen-public-icons.mjs``, which bakes the
``<x>_icon="…"`` arguments of this tag.
"""

from __future__ import annotations

from django import template
from django.shortcuts import resolve_url

register = template.Library()


@register.inclusion_tag("public/components/button.html")
def button(
    *,
    href,
    label,
    arg=None,
    query="",
    fill="solid",
    size="",
    color="",
    block=False,
    start_icon="",
    end_icon="",
    icon_size=None,
    label_class="",
    extra_class="",
    id="",
    testid="",
):
    url = resolve_url(href, *([arg] if arg else []))
    looks = [fill if fill != "solid" else "", size, color, "block" if block else ""]
    classes = [f"ep-button--{look}" for look in looks if look]
    if extra_class:
        classes.append(extra_class)
    return {
        "url": f"{url}?{query}" if query else url,
        "label": label,
        "modifiers": "".join(f" {name}" for name in classes),
        "start_icon": start_icon,
        "end_icon": end_icon,
        "icon_size": icon_size,
        "label_class": label_class,
        "id": id,
        "testid": testid,
    }
