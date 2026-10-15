"""System check of the fiscal gateway: the platform's hub is a reserved slug (``fiscal_gateway.E001``).

``PLATFORM_HUB_SLUG`` names the one hub that presents ERPlora's own records through its seal without an
authorisation (``internal.py``). A business able to register that slug would present in ERPlora's name too,
so it must be one of ``live.slugs``' reserved names; ``check`` (``migrate`` and the deploy run it) refuses
to start otherwise.
"""

from django.conf import settings
from django.core import checks
from live.slugs import is_reserved_hub_slug


@checks.register(checks.Tags.security)
def check_platform_hub_slug(app_configs=None, **kwargs):
    slug = getattr(settings, "PLATFORM_HUB_SLUG", "") or ""
    if is_reserved_hub_slug(slug):
        return []
    return [
        checks.Error(
            f"PLATFORM_HUB_SLUG {slug!r} is not a reserved hub slug: a business could take it and "
            "present through ERPlora's seal in ERPlora's name.",
            hint="Use a slug of live.slugs.RESERVED_HUB_SLUGS (the default is 'erplora').",
            id="fiscal_gateway.E001",
        )
    ]
