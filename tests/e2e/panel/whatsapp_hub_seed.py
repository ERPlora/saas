"""The erplora.com side of WhatsApp's cross e2e with a real Hub (whatsapp-hub.spec.ts): ``a`` with its number.

``uv run python tests/e2e/panel/whatsapp_hub_seed.py <id of a> <id of b>`` from the SaaS checkout that runs beside
the Hub's stack (its ``DB_NAME``; development only: refused without ``DEBUG``). The ids are the Hub's own for its
local hubs (``seed_local_hubs`` gives them theirs), so that the snapshot erplora.com pushes (``PUT
/internal/hubs/{id}/state``) names the business the Hub knows. It then:

- seeds ``demo_seed``'s accounts and businesses, ``a`` and ``b`` taking those ids (a database seeded before with
  other ids is refused: it is the run's own, drop it and create it again);
- connects ``NUMBER_ID`` to ``a`` (a made-up permission, encrypted as any other: Meta is never called);
- announces the channel as connecting it does (a newer snapshot) and pushes it to the Hub, printing one JSON line:
  ``{"delivered": true|false, "hub_error": "<the Hub's refusal code>"}``.

Running it again keeps what exists and pushes once more.
"""

import json
import os
import sys
from pathlib import Path
from uuid import UUID

SAAS_DIR = Path(__file__).resolve().parents[3]
SLUGS = ("a", "b")
#: Meta's ids of ``a``'s number and of its WhatsApp Business account (whatsapp-hub.spec.ts signs Meta's webhook for them).
NUMBER_ID = "880000000000101"
WABA_ID = "880000000000100"


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def seed(ids: dict[str, UUID]) -> dict:
    from django.core.management import call_command
    from django.db import transaction

    from hubs import services
    from hubs.models import Hub
    from whatsapp.models import PhoneNumber

    missing = []
    for slug in SLUGS:
        existing = Hub.objects.filter(slug=slug).values_list("id", flat=True).first()
        if existing is None:
            missing.append(ids[slug])
        elif existing != ids[slug]:
            raise SystemExit(f"whatsapp_hub_seed.py: {slug} is {existing} here and {ids[slug]} in the Hub: drop this database.")
    # demo_seed creates the missing businesses in SLUGS' order: each takes the Hub's id for it.
    field = Hub._meta.get_field("id")
    original, field.default = field.default, iter(missing).__next__
    try:
        call_command("demo_seed", verbosity=0)
    finally:
        field.default = original

    hub = Hub.objects.get(slug="a")
    PhoneNumber.objects.update_or_create(
        phone_number_id=NUMBER_ID,
        defaults={
            "hub": hub,
            "display_phone": "+34 910 00 01 01",
            "display_name": "E2E Peluquería",
            "waba_id": WABA_ID,
            "access_token": "EAAG-e2e-made-up",
            "is_active": True,
            "needs_reconnect": False,
        },
    )
    with transaction.atomic():
        services.bump_state(hub.id)
    delivered = services.sync_hub(hub.id)
    return {"delivered": delivered, "hub_error": Hub.objects.get(pk=hub.id).last_hub_error}


def main(arguments: list[str]) -> None:
    if len(arguments) != 2:
        raise SystemExit("Usage: whatsapp_hub_seed.py <id of a in the Hub> <id of b in the Hub>")
    setup_django()
    from django.conf import settings

    if not settings.DEBUG:
        raise SystemExit("whatsapp_hub_seed.py: development only (DEBUG=True).")
    print(json.dumps(seed(dict(zip(SLUGS, (UUID(value) for value in arguments), strict=True)))))


if __name__ == "__main__":
    main(sys.argv[1:])
