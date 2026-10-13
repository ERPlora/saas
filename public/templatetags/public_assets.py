"""``{% public_assets %}``: the ``<link>`` and ``<script>`` tags of the public web's Vite entry.

``frontend/public.ts`` (spec §8.4) registers the ``ion-*`` the templates use and brings Ionic's CSS,
the ``@erplora/ui`` tokens and the public stylesheets. The files come from ``live.spa.spa_assets``
(the build's manifest, or the dev server with DEBUG); every script and modulepreload carries the
response's CSP nonce, as ``'strict-dynamic'`` requires. Used once, in ``public/public_base.html``.
"""

from __future__ import annotations

from django import template
from django.core.exceptions import ImproperlyConfigured
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString
from live.spa import spa_assets

register = template.Library()

#: The manifest key of the public entry (``build.rollupOptions.input`` in vite.config.ts).
PUBLIC_ENTRY = "frontend/public.ts"


@register.simple_tag(takes_context=True)
def public_assets(context) -> SafeString:
    nonce = context.get("csp_nonce")
    if not nonce:
        raise ImproperlyConfigured(
            "The public pages need django.middleware.csp.ContentSecurityPolicyMiddleware and the csp "
            "context processor: without a nonce, 'strict-dynamic' blocks every script."
        )
    assets = spa_assets(context["request"], entry=PUBLIC_ENTRY)
    styles = format_html_join(
        "\n", '<link rel="stylesheet" href="{}">', ((href,) for href in assets["css"])
    )
    preloads = format_html_join(
        "\n",
        '<link rel="modulepreload" href="{}" nonce="{}">',
        ((href, nonce) for href in assets["preload"]),
    )
    scripts = format_html_join(
        "\n",
        '<script type="module" src="{}" nonce="{}"></script>',
        ((src, nonce) for src in assets["scripts"]),
    )
    return format_html("{}\n{}\n{}", styles, preloads, scripts)
