"""The erplora.com side of WhatsApp's cross e2e with a real Hub (whatsapp-hub.spec.ts): ``a`` with its number.

``uv run python tests/e2e/panel/whatsapp_hub_seed.py <id of a> <id of b> [--used N]`` from the SaaS checkout that runs
beside the Hub's stack (its ``DB_NAME``; development only: refused without ``DEBUG``). The ids are the Hub's own for its
local hubs (``seed_local_hubs`` gives them theirs), so that the snapshot erplora.com pushes (``PUT
/internal/hubs/{id}/state``) names the business the Hub knows. It then:

- seeds ``demo_seed``'s accounts and businesses, ``a`` and ``b`` taking those ids (a database seeded before with
  other ids is refused: it is the run's own, drop it and create it again);
- connects ``NUMBER_ID`` to ``a`` (a made-up permission, encrypted as any other: Meta is never called);
- keeps ``a``'s templates as erplora.com does after reading Meta's list (``TEMPLATES``, in Meta's own shape, through
  ``templates.from_meta`` and ``whatsapp.template.sync``): approved, in review, rejected with Meta's reason, and one
  made in WhatsApp Manager with a photo header and a named variable. Their names start with ``e2e_``, as what the
  Hub's e2e delete after a run (its ``whatsapp-helpers.ts``, ``cleanUp``);
- sets ``a``'s usage of this calendar month (UTC) to ``--used`` (0 by default: no send of the e2e is stopped; the
  plan's allowance makes the send that reaches it refused, ``whatsapp.cap_reached``, before Meta is called);
- announces the channel as connecting it does (a newer snapshot) and pushes it to the Hub, printing one JSON line:
  ``{"delivered": true|false, "hub_error": "<the Hub's refusal code>"}`` (the Hub's e2e compare it whole).

Running it again keeps what exists (one of each template), sets the month's usage again and pushes once more.
"""

import argparse
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
#: ``a``'s templates as Meta's list gives them (``GET /<WABA_ID>/message_templates``: ``id, name, language, category,
#: status, rejected_reason, components``), for the Hub's WHATSAPP_INBOX-F27 (Meta's verdict and reason) and F28 (one
#: made in WhatsApp Manager the Hub cannot fill).
TEMPLATES = (
    {
        "id": "880000000000201",
        "name": "e2e_seed_recordatorio_cita",
        "language": "es",
        "category": "UTILITY",
        "status": "APPROVED",
        "rejected_reason": "NONE",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Tu cita"},
            {
                "type": "BODY",
                "text": "Hola {{1}}, te esperamos el {{2}}.",
                "example": {"body_text": [["Ana", "viernes"]]},
            },
            {"type": "FOOTER", "text": "Peluquería e2e"},
            {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Confirmar"}]},
        ],
    },
    {
        "id": "880000000000202",
        "name": "e2e_seed_oferta_color",
        "language": "es",
        "category": "MARKETING",
        "status": "PENDING",
        "rejected_reason": "NONE",
        "components": [
            {
                "type": "BODY",
                "text": "Hola {{1}}, este mes el color tiene un 10 % de descuento.",
                "example": {"body_text": [["Ana"]]},
            },
        ],
    },
    {
        "id": "880000000000203",
        "name": "e2e_seed_cambio_horario",
        "language": "es",
        "category": "UTILITY",
        "status": "REJECTED",
        "rejected_reason": "INVALID_FORMAT",
        "components": [
            {
                "type": "BODY",
                "text": "Cambiamos el horario: abrimos de {{1}} a {{2}}.",
                "example": {"body_text": [["9:00", "20:00"]]},
            },
        ],
    },
    {
        "id": "880000000000204",
        "name": "e2e_seed_bienvenida_foto",
        "language": "es",
        "category": "MARKETING",
        "status": "APPROVED",
        "rejected_reason": "NONE",
        "components": [
            {"type": "HEADER", "format": "IMAGE", "example": {"header_handle": ["4::aW1hZ2UvanBlZw=="]}},
            {
                "type": "BODY",
                "text": "Hola {{nombre}}, te damos la bienvenida al salón.",
                "example": {"body_text_named_params": [{"param_name": "nombre", "example": "Ana"}]},
            },
        ],
    },
)


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def seed(ids: dict[str, UUID], used: int = 0) -> dict:
    from django.core.management import call_command
    from django.db import transaction
    from django.utils import timezone

    from hubs import services
    from hubs.models import Hub
    from whatsapp import services as whatsapp_services
    from whatsapp import templates
    from whatsapp.models import PhoneNumber, Usage
    from whatsapp.schemas import TemplateSyncIn

    missing = []
    for slug in SLUGS:
        existing = Hub.objects.filter(slug=slug).values_list("id", flat=True).first()
        if existing is None:
            missing.append(ids[slug])
        elif existing != ids[slug]:
            raise SystemExit(f"whatsapp_hub_seed.py: {slug} is {existing} here and {ids[slug]} in the Hub: drop this database.")
    # demo_seed creates the missing businesses in SLUGS' order: each takes the Hub's id for it.
    field = Hub._meta.get_field("id")
    original = field.default
    # A field caches the callable of its default (``_get_default``): dropped on both sides, the swap takes and goes.
    field.__dict__.pop("_get_default", None)
    field.default = iter(missing).__next__
    try:
        call_command("demo_seed", verbosity=0)
    finally:
        field.default = original
        field.__dict__.pop("_get_default", None)

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
    # What erplora.com writes after reading Meta's list (gateway.sync_templates), without calling Meta. Not
    # ``complete``: a template the run added stays, as one Meta's list did not reach.
    items = [mirror for mirror in map(templates.from_meta, TEMPLATES) if mirror is not None]
    whatsapp_services.template_sync(
        whatsapp_services.platform_context(), TemplateSyncIn(hub_id=hub.id, items=items, complete=False)
    )
    with transaction.atomic():
        usage, _ = Usage.objects.get_or_create(hub=hub, month=timezone.now().strftime("%Y-%m"))
        usage.used = used
        usage.full_clean()
        usage.save(update_fields=["used", "updated_at"])
        services.bump_state(hub.id)
    delivered = services.sync_hub(hub.id)
    return {"delivered": delivered, "hub_error": Hub.objects.get(pk=hub.id).last_hub_error}


def whole_number(value: str) -> int:
    """``--used``: a count of messages, a whole number not below zero."""
    if not (value.isascii() and value.isdigit()):
        raise argparse.ArgumentTypeError(f"a whole number not below zero, not {value!r}")
    return int(value)


def main(arguments: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="whatsapp_hub_seed.py", description="erplora.com's side of the cross e2e.")
    parser.add_argument("a", type=UUID, help="the id of a in the Hub")
    parser.add_argument("b", type=UUID, help="the id of b in the Hub")
    parser.add_argument("--used", type=whole_number, default=0, help="a's WhatsApp messages sent this month (0)")
    options = parser.parse_args(arguments)
    setup_django()
    from django.conf import settings

    if not settings.DEBUG:
        raise SystemExit("whatsapp_hub_seed.py: development only (DEBUG=True).")
    print(json.dumps(seed({"a": options.a, "b": options.b}, used=options.used)))


if __name__ == "__main__":
    main(sys.argv[1:])
