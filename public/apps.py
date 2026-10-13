from live.meta import LiveAppConfig


class PublicConfig(LiveAppConfig):
    """The public web of erplora.com in Django templates (SEO): landing, pricing, legal pages, the
    app catalogue, robots.txt, llms.txt, the sitemap, the cookie consent and the error pages. A
    platform app (``kind = "platform"``): always on, at the project root next to ``base/`` (round
    15, PLAN §20.2). No menu and no permissions of its own."""

    name = "public"
    label = "public"
    kind = "platform"
    verbose_name = "Public web"
