"""The rows the AI gateway's specs open: its admin (assistant-admin.spec.ts: ASSISTANT-F01, F02, F04, F05 and F07) and
the Hub's doors with «Assistant usage records» (assistant-gateway.spec.ts: ASSISTANT-F11 to F24).

``uv run python tests/e2e/panel/assistant_seed.py <action> [<provider address>]`` from the SaaS, against the run's
database (development only: known passwords, refused without ``DEBUG``). Every action starts from ``clear``, so a
run always finds the same rows; ``clear`` removes every account ``e2e-assistant-*@example.com``, every provider whose
identifier starts with ``e2e-`` (its keys and models with it) and the choice of the model that answers when it named
one of them, every business whose address starts with ``e2e-assistant-`` (its usage with it) and the usage of the
demo ``demo-0e2ea55e``.

- ``staff``: ``e2e-assistant-admin`` (ERPlora's staff with every permission of the gateway) and
  ``e2e-assistant-viewer`` (staff who may only look at the providers, models and the model that answers).
- ``provider <address>``: ``staff`` plus «E2E Local», an OpenAI-compatible provider at ``<address>`` (the e2e's
  ``assistant.tests.fake_provider``) with a made-up key ending in ``e2e1``, without models.
- ``models <address>``: ``provider`` plus its models ``gpt-e2e-large`` (1 / 2 USD per million tokens) and
  ``gpt-e2e-mini``.
- ``gateway <address>``: ``models`` with ``gpt-e2e-large`` answering, and two working businesses on the Free plan
  (no subscription): ``e2e-assistant-bar`` with its allowance whole and ``e2e-assistant-spent`` with this month's
  messages spent. Prints one line of JSON for the spec: the plan's allowance and the addresses of the businesses and
  of the demo (the spec signs with ``fixtures.internalSecret``, as the Hub would).

No real key is ever written: the key here is made up and the provider is the local fake one.
"""

import json
import os
import sys
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[3]
PASSWORD = os.environ.get("QA_PANEL_PASSWORD", "e2e-panel")
DOMAIN = "@example.com"
PREFIX = "e2e-assistant-"
PROVIDER = "e2e-local"
BUSINESS_PREFIX = "e2e-assistant-"
DEMO = "demo-0e2ea55e"
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

    from assistant.models import AIProvider, AIRoutingPolicy, AssistantUsage
    from hubs.models import Hub

    AssistantUsage.objects.filter(demo=DEMO).delete()
    Hub.objects.filter(slug__startswith=BUSINESS_PREFIX).delete()
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


def models(address: str):
    from assistant.models import AIModel

    local = provider(address)
    large = AIModel.objects.create(
        provider=local, model_id="gpt-e2e-large", display_name="Large", price_input_per_1m="1", price_output_per_1m="2"
    )
    AIModel.objects.create(provider=local, model_id="gpt-e2e-mini", display_name="Mini")
    return large


def gateway(address: str) -> dict:
    from django.utils import timezone

    from assistant import queries
    from assistant.models import AIRoutingPolicy, AssistantUsage
    from hubs.models import Hub, Plan

    policy = AIRoutingPolicy.solo()
    policy.active_model = models(address)
    policy.fallback_model = None
    policy.save()
    now = timezone.now()
    limit = Plan.objects.get(slug="free").assistant_messages_per_month

    def business(local: str, name: str) -> Hub:
        return Hub.objects.create(
            slug=f"{BUSINESS_PREFIX}{local}",
            name=name,
            country="ES",
            status=Hub.Status.ACTIVE,
            ready_at=now,
        )

    bar = business("bar", "E2E Bar Asistente")
    spent = business("spent", "E2E Sin Mensajes")
    AssistantUsage.objects.create(hub=spent, month=queries.month_of(now), messages=limit)
    return {
        "limit": limit,
        "bar": bar.slug,
        "spent": spent.slug,
        "demo": DEMO,
    }


def main(action: str, address: str) -> None:
    setup_django()
    from django.conf import settings
    from django.db import transaction

    if not settings.DEBUG:
        sys.exit("assistant_seed.py only runs with DEBUG=True")
    actions = {
        "clear": lambda: None,
        "staff": staff,
        "provider": lambda: provider(address),
        "models": lambda: models(address),
        "gateway": lambda: gateway(address),
    }
    if action not in actions:
        sys.exit(f"unknown action {action!r}: one of {', '.join(actions)}")
    with transaction.atomic():
        clear()
        made = actions[action]()
    print(json.dumps(made) if isinstance(made, dict) else f"{action}: assistant e2e rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "staff", sys.argv[2] if len(sys.argv) > 2 else "")
