"""The rows the AI gateway's specs open: its admin (assistant-admin.spec.ts: ASSISTANT-F01, F02, F04, F05 and F07), the
Hub's doors with «Assistant usage records» (assistant-gateway.spec.ts: ASSISTANT-F11 to F24) and the panel's own
assistant (assistant-panel.spec.ts: ASSISTANT-F25 and F26).

``uv run python tests/e2e/panel/assistant_seed.py <action> [<provider address>] [<language>]`` from the SaaS, against the run's
database (development only: known passwords, refused without ``DEBUG``). Every action starts from ``clear``, so a
run always finds the same rows; ``clear`` removes every account ``e2e-assistant-*@example.com``, every provider whose
identifier starts with ``e2e-`` (its keys and models with it) and the choice of the model that answers when it named
one of them, every business whose address starts with ``e2e-assistant-`` or that one of those accounts owns (its usage
and its people's access with it) and the usage of the demo ``demo-0e2ea55e``; an account's month of messages goes with
the account.

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
- ``panel <address> [<language>]``: ``gpt-e2e-large`` answering, as in ``gateway``, and ``e2e-assistant-owner``: an
  account like any other (no staff), in ``language`` (``es`` by default), owner of one working business on the Free
  plan, «E2E Asistente Panel». Prints one line of JSON for the spec: the owner's email, the business and its address.

- ``forget``: ``clear`` and the real keys of ``real`` deleted (on the run's own e2e database only): what the probes'
  spec (``assistant-probes.spec.ts``) runs after every worker, so no real key stays behind.
- ``real [<language>]``: the QA battery with the real model (``assistant-battery.spec.ts``, only with
  ``QA_REAL_PROVIDER=1``, never in the CI), on the run's own e2e database only (``saas_…_e2e…``; the shared ``saas`` is
  refused). ``staff`` plus the real providers as production has them, each through the gateway's operations: «Qwen»
  (``qwen``, OpenAI's API at Alibaba's Frankfurt workspace) with ``qwen3.7-plus`` answering, and «OpenAI» (``openai``,
  ``assistant.credential.import`` as ``import_ai_keys_from_env`` does) with ``gpt-5.4-mini`` as the fallback and the
  embeddings of the documentation search (``ASSISTANT_SERVICE_PROVIDER=openai``). Their keys are read from
  ``QA_QWEN_API_KEY`` and ``QA_OPENAI_API_KEY`` only, never printed. Then ``e2e-assistant-qa-battery``, an account like
  any other in ``language``, owner of one working business on the Free plan, «QA Base». Prints one line of JSON: the
  owner's email, the business, its address and the models.

The other actions never write a real key: theirs is made up and the provider is the local fake one.
"""

import json
import os
import re
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
#: The real providers of ``real``, as production has them (each key from its variable of the environment).
QWEN = {
    "slug": "qwen",
    "name": "Qwen",
    "base_url": "https://ws-7mg25evt3ic2ow02.eu-central-1.maas.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3.7-plus",
    "display_name": "Qwen3.7-Plus",
    "key": "QA_QWEN_API_KEY",
}
OPENAI = {"slug": "openai", "model": "gpt-5.4-mini", "display_name": "GPT-5.4 mini", "key": "QA_OPENAI_API_KEY"}
#: The run's own e2e database (tests/e2e/stack.ts, ``isE2eDatabase``): the only one ``real`` writes real keys into.
E2E_DATABASE = re.compile(r"^saas(?:_[a-z0-9]+)*_e2e(?:_[a-z0-9]+)*$")


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def clear() -> None:
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from accounts.models import HubMembership
    from assistant.models import AIProvider, AIRoutingPolicy, AssistantUsage
    from hubs.models import Hub

    AssistantUsage.objects.filter(demo=DEMO).delete()
    # Its businesses, also the ones the assistant created for an account of this seed (the battery's «QA Asistente 31»).
    owned = Hub.objects.filter(members__user__email__startswith=PREFIX, members__user__email__endswith=DOMAIN)
    slugs = Q(slug__startswith=BUSINESS_PREFIX) | Q(pk__in=owned.values("pk"))
    HubMembership.objects.filter(hub_slug__in=Hub.objects.filter(slugs).values("slug")).delete()
    HubMembership.objects.filter(hub_slug__startswith=BUSINESS_PREFIX).delete()
    Hub.objects.filter(slugs).delete()
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


def answering(address: str) -> None:
    """``models`` with ``gpt-e2e-large`` answering, without a model in reserve."""
    from assistant.models import AIRoutingPolicy

    policy = AIRoutingPolicy.solo()
    policy.active_model = models(address)
    policy.fallback_model = None
    policy.save()


def gateway(address: str) -> dict:
    from django.utils import timezone

    from assistant import queries
    from assistant.models import AssistantUsage
    from hubs.models import Hub, Plan

    answering(address)
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


def panel(address: str, language: str = "es") -> dict:
    answering(address)
    owner, hub = _owner_with_business("owner", ("Lena", "Panel"), "E2E Asistente Panel", "panel", language)
    return {"owner": owner.email, "business": hub.name, "slug": hub.slug}


def _owner_with_business(local: str, names: tuple[str, str], business: str, slug: str, language: str):
    """An account like any other (no staff), in ``language``, owner of one working business on the Free plan."""
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from accounts.models import HubMembership
    from hubs.models import Hub, HubMember

    owner = get_user_model().objects.create_user(
        email=f"{PREFIX}{local}{DOMAIN}", password=PASSWORD, language=language, first_name=names[0], last_name=names[1]
    )
    # Proven address: every account proves it before its first session (the code a sign-up mails).
    EmailAddress.objects.create(user=owner, email=owner.email, verified=True, primary=True)
    now = timezone.now()
    hub = Hub.objects.create(
        slug=f"{BUSINESS_PREFIX}{slug}",
        name=business,
        country="ES",
        language=language,
        status=Hub.Status.ACTIVE,
        ready_at=now,
    )
    HubMember.objects.create(hub=hub, user=owner, role=HubMember.Role.OWNER, joined_at=now, accepted_at=now)
    HubMembership.objects.create(user=owner, hub_slug=hub.slug, role=HubMembership.Role.OWNER)
    return owner, hub


def _secret(name: str) -> str:
    """A key of the environment, never printed: the refusal names only the variable."""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"real: export {name} (see tests/e2e/README.md, «El asistente con el modelo de verdad»)")
    return value


def _chosen(ctx, provider, model: dict):
    """``model`` of ``provider``, chosen as the admin does (``assistant.model.select``)."""
    from assistant import services
    from assistant.models import AIModel
    from assistant.schemas import ListedModel, ModelSelectIn

    listed = ListedModel(model_id=model["model"], display_name=model["display_name"])
    services.model_select(ctx, ModelSelectIn(provider=provider.pk, listed=[listed], selected=[model["model"]]))
    return AIModel.objects.get(provider=provider, model_id=model["model"])


def e2e_only(action: str, database: str | None = None) -> None:
    """Refuses ``action`` (``real``, ``forget``) on any database but the run's own e2e one (``database``, the
    configured one by default): never the shared ``saas`` of a developer."""
    if database is None:
        from django.conf import settings

        database = settings.DATABASES["default"]["NAME"]
    if not E2E_DATABASE.match(database):
        sys.exit(f"{action}: only on the run's own e2e database (saas_…_e2e…), never on {database!r}")


def real_keys() -> tuple[str, str]:
    """The keys of ``real``, before anything is cleared: only on the run's own e2e database, never the shared one."""
    e2e_only("real")
    return _secret(QWEN["key"]), _secret(OPENAI["key"])


def forget() -> None:
    """The real keys ``real`` saved (Qwen's and OpenAI's credentials) taken out of the e2e database: the probes' spec
    runs it after every worker (with ``clear`` before, the QA accounts go too). The providers and models stay, keyless;
    the next ``real`` saves the keys again from the environment."""
    from assistant.models import AIProviderCredential

    AIProviderCredential.objects.filter(provider__slug__in=(QWEN["slug"], OPENAI["slug"])).delete()


def real(keys: tuple[str, str], language: str = "es") -> dict:
    from django.contrib.auth import get_user_model
    from live.context import OperationContext, Scope

    from assistant import services
    from assistant.models import AIProvider, AIProviderCredential
    from assistant.schemas import CredentialImportIn, CredentialIn, PolicyIn

    qwen_key, openai_key = keys
    staff()
    admin = get_user_model().objects.get(email=f"{PREFIX}admin{DOMAIN}")
    # The member of the staff acting, as ``assistant.admin.staff_context`` builds it for the admin's pages.
    ctx = OperationContext(
        scope=Scope("user", str(admin.pk)), actor=admin, permissions=frozenset({"assistant.manage"}), language="en"
    )
    qwen = AIProvider.objects.filter(slug=QWEN["slug"]).first()
    if qwen is None:
        # Added as the admin's form adds it: its fields validated (the address over https).
        qwen = AIProvider(slug=QWEN["slug"], name=QWEN["name"], kind=AIProvider.Kind.OPENAI, base_url=QWEN["base_url"])
        qwen.full_clean()
        qwen.save()
    kept = AIProviderCredential.objects.filter(provider=qwen, label="default").first()
    services.credential_save(
        ctx, CredentialIn(provider=qwen.pk, id=kept.pk if kept else None, label="default", api_key=qwen_key)
    )
    services.credential_import(
        services.platform_context(), CredentialImportIn(kind="openai", api_key=openai_key, label="default", force=True)
    )
    openai = AIProvider.objects.get(slug=OPENAI["slug"])
    answers, fallback = _chosen(ctx, qwen, QWEN), _chosen(ctx, openai, OPENAI)
    services.policy_update(ctx, PolicyIn(active_model=answers.pk, fallback_model=fallback.pk))

    owner, hub = _owner_with_business("qa-battery", ("Quique", "Battery"), "QA Base", "qa-base", language)
    return {
        "owner": owner.email,
        "business": hub.name,
        "slug": hub.slug,
        "model": f"{answers.model_id} ({qwen.name})",
        "fallback": f"{fallback.model_id} ({openai.name})",
    }


def main(action: str, address: str, language: str) -> None:
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
        "panel": lambda: panel(address, language),
        "real": lambda: real(keys, language),
        "forget": forget,
    }
    if action not in actions:
        sys.exit(f"unknown action {action!r}: one of {', '.join(actions)}")
    keys = real_keys() if action == "real" else ("", "")
    if action == "forget":
        e2e_only(action)
    with transaction.atomic():
        clear()
        made = actions[action]()
    print(json.dumps(made) if isinstance(made, dict) else f"{action}: assistant e2e rows")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "staff"
    # ``real`` takes no provider address: ``real [<language>]``.
    rest = ["", *sys.argv[2:]] if action == "real" else sys.argv[2:]
    main(action, rest[0] if rest else "", rest[1] if len(rest) > 1 else "es")
