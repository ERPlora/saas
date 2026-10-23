"""The rows the AI gateway's admin spec opens (assistant-admin.spec.ts: ASSISTANT-F01, F02, F04, F05 and F07).

``uv run python tests/e2e/panel/assistant_seed.py <action> [<provider address>]`` from the SaaS, against the run's
database (development only: known passwords, refused without ``DEBUG``). Every action starts from ``clear``, so a
run always finds the same rows; ``clear`` removes every account ``e2e-assistant-*@example.com``, every provider whose
identifier starts with ``e2e-`` (its keys and models with it) and the choice of the model that answers when it named
one of them.

- ``staff``: ``e2e-assistant-admin`` (ERPlora's staff with every permission of the gateway) and
  ``e2e-assistant-viewer`` (staff who may only look at the providers, models and the model that answers).
- ``provider <address>``: ``staff`` plus «E2E Local», an OpenAI-compatible provider at ``<address>`` (the e2e's
  ``assistant.tests.fake_provider``) with a made-up key ending in ``e2e1``, without models.
- ``models <address>``: ``provider`` plus its models ``gpt-e2e-large`` (1 / 2 USD per million tokens) and
  ``gpt-e2e-mini``.

No real key is ever written: the key here is made up and the provider is the local fake one.
"""

import os
import sys
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
PASSWORD = os.environ.get("QA_PANEL_PASSWORD", "e2e-panel")
DOMAIN = "@example.com"
PREFIX = "e2e-assistant-"
PROVIDER = "e2e-local"
#: A made-up key in the shape of OpenAI's.
API_KEY = "sk-e2e-0000000000000000000000000000e2e1"
VIEW_ONLY = ("view_aiprovider", "view_aiprovidercredential", "view_aimodel", "view_airoutingpolicy")


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from assistant.models import AIProvider, AIRoutingPolicy

    ours = AIProvider.objects.filter(slug__startswith="e2e-")
    AIRoutingPolicy.objects.filter(
        Q(active_model__provider__in=ours) | Q(fallback_model__provider__in=ours)
    ).update(active_model=None, fallback_model=None)
    ours.delete()
    get_user_model().objects.filter(email__startswith=PREFIX, email__endswith=DOMAIN).delete()


def _account(local: str, codenames):
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    user = get_user_model().objects.create_user(
        email=f"{PREFIX}{local}{DOMAIN}", password=PASSWORD, language="en", first_name=local.title(), is_staff=True
    )
    # Proven address: every account proves it before its first session (the code a sign-up mails).
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    permissions = Permission.objects.filter(content_type__app_label="assistant")
    if codenames is not None:
        permissions = permissions.filter(codename__in=codenames)
    user.user_permissions.add(*permissions)
    return user


def staff() -> None:
    _account("admin", None)
    _account("viewer", VIEW_ONLY)


def provider(address: str):
    from assistant.models import AIProvider, AIProviderCredential

    staff()
    local = AIProvider.objects.create(slug=PROVIDER, name="E2E Local", kind="openai", base_url=address)
    AIProviderCredential.objects.create(provider=local, label="default", api_key=API_KEY, key_hint=API_KEY[-4:])
    return local


def models(address: str) -> None:
    from assistant.models import AIModel

    local = provider(address)
    AIModel.objects.create(
        provider=local, model_id="gpt-e2e-large", display_name="Large", price_input_per_1m="1", price_output_per_1m="2"
    )
    AIModel.objects.create(provider=local, model_id="gpt-e2e-mini", display_name="Mini")


def main(action: str, address: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("assistant_seed.py only runs with DEBUG=True")
    actions = {"clear": lambda: None, "staff": staff, "provider": lambda: provider(address), "models": lambda: models(address)}
    if action not in actions:
        sys.exit(f"unknown action {action!r}: one of {', '.join(actions)}")
    with transaction.atomic():
        clear()
        actions[action]()
    print(f"{action}: assistant e2e rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "staff", sys.argv[2] if len(sys.argv) > 2 else "")
