"""System check of the fiscal gateway: the names of the platform's hub are reserved slugs (``fiscal_gateway.E001``).

``PLATFORM_HUB_SLUGS`` names the one hub that presents ERPlora's own records through its seal without an
authorisation (``internal.py``). A business able to register one of those slugs would present in ERPlora's name
too, so each must be one of ``live.slugs``' reserved names; ``check`` (``migrate`` and the deploy run it) refuses
to start otherwise.
"""

from django.conf import settings
from django.core import checks
from live.slugs import is_reserved_hub_slug


@checks.register(checks.Tags.security)
def check_platform_hub_slugs(app_configs=None, **kwargs):
    return [
        checks.Error(
            f"PLATFORM_HUB_SLUGS: {slug!r} is not a reserved hub slug: a business could take it and "
            "present through ERPlora's seal in ERPlora's name.",
            hint="Use slugs of live.slugs.RESERVED_HUB_SLUGS.",
            id="fiscal_gateway.E001",
        )
        for slug in settings.PLATFORM_HUB_SLUGS
        if not is_reserved_hub_slug(slug)
    ]
