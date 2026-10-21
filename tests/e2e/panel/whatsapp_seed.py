"""The business with a connected WhatsApp number that WhatsApp's spec writes to (whatsapp.spec.ts).

``uv run python tests/e2e/panel/whatsapp_seed.py seed|clear`` from saas-next/, against the database of the run
(development only: refused without ``DEBUG``). ``seed`` starts from ``clear``. Rows are written with the ORM: Meta is
never called (the spec signs Meta's webhook itself) and the Hub is the spec's double.

- ``e2e-whatsapp-bar`` (owner ``e2e-whatsapp@example.com``), with the number ``NUMBER_ID`` connected (a made-up
  permission, encrypted as any other).
"""

import os
import sys
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
EMAIL = "e2e-whatsapp@example.com"
SLUG = "e2e-whatsapp-bar"
#: Meta's id of the business's number (whatsapp.spec.ts signs a webhook for it).
NUMBER_ID = "880000000000001"


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model

    from hubs.models import BillingProfile, Hub
    from whatsapp.models import PhoneNumber

    PhoneNumber.objects.filter(phone_number_id=NUMBER_ID).delete()
    hubs = Hub.objects.filter(slug=SLUG)
    profiles = list(hubs.values_list("billing_profile_id", flat=True))
    hubs.delete()
    BillingProfile.objects.filter(pk__in=profiles).delete()
    get_user_model().objects.filter(email=EMAIL).delete()


def seed() -> None:
    from django.contrib.auth import get_user_model

    from hubs.models import Hub
    from hubs.tests.conftest import create_business
    from whatsapp.models import PhoneNumber

    owner = get_user_model().objects.create_user(email=EMAIL, password=None, language="es")
    hub = create_business(owner, name="E2E WhatsApp Bar")
    Hub.objects.filter(pk=hub.pk).update(slug=SLUG, status=Hub.Status.ACTIVE)
    PhoneNumber.objects.create(
        hub_id=hub.pk,
        phone_number_id=NUMBER_ID,
        display_phone="+34 910 00 00 00",
        display_name="E2E WhatsApp Bar",
        waba_id="880000000000000",
        access_token="EAAG-e2e-made-up",
    )


def main(action: str) -> None:
    setup_django()
    from django.conf import settings

    if not settings.DEBUG:
        raise SystemExit("whatsapp_seed.py: development only (DEBUG=True).")
    clear()
    if action == "seed":
        seed()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("seed", "clear"):
        raise SystemExit("Usage: whatsapp_seed.py seed|clear")
    main(sys.argv[1])
