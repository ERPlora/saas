"""ASSISTANT-F25 · The rows the panel's assistant's e2e opens (``tests/e2e/panel/assistant_seed.py panel``, the one
``panel/assistant-panel.spec.ts`` runs): the e2e's model answering, at the address of the spec's own provider, and
``e2e-assistant-owner``, an account like any other (no staff) with one working business, in the language the spec
asks for. ``clear`` leaves nothing of it behind: the account, its business, its access and its month's messages.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import HubMembership
from assistant import queries
from assistant.models import AIRoutingPolicy, AssistantUsage
from assistant.tests.conftest import fernet_key  # noqa: F401 - the credentials' key
from hubs.models import Hub, HubMember
from hubs.tests.conftest import plans  # noqa: F401 - the catalogue of plans

SEED = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "panel" / "assistant_seed.py"
ADDRESS = "http://127.0.0.1:8017/v1"

pytestmark = pytest.mark.django_db


def _load():
    spec = importlib.util.spec_from_file_location("assistant_seed", SEED)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seed(monkeypatch, fernet_key, plans):  # noqa: F811 - the fixtures above
    """The seed as a module; pytest set Django up already (its ``setup_django`` would configure the logging again)."""
    module = _load()
    monkeypatch.setattr(module, "setup_django", lambda: None)
    return module


def test_the_owner_is_an_account_like_any_other_with_one_working_business(seed):
    made = seed.panel(ADDRESS)

    owner = get_user_model().objects.get(email="e2e-assistant-owner@example.com")
    assert made == {"owner": owner.email, "business": "E2E Asistente Panel", "slug": "e2e-assistant-panel"}
    assert not owner.is_staff and not owner.is_superuser
    assert owner.language == "es"
    assert owner.check_password(seed.PASSWORD)
    assert owner.emailaddress_set.get().verified
    hub = Hub.objects.get(slug="e2e-assistant-panel")
    assert (hub.name, hub.status, hub.ready_at is not None) == ("E2E Asistente Panel", Hub.Status.ACTIVE, True)
    assert list(HubMember.objects.filter(user=owner).values_list("hub__slug", "role")) == [
        ("e2e-assistant-panel", HubMember.Role.OWNER)
    ]
    assert HubMembership.objects.filter(user=owner, hub_slug=hub.slug).exists()


def test_the_e2e_model_answers_at_the_spec_provider(seed):
    seed.panel(ADDRESS)

    policy = AIRoutingPolicy.solo()
    assert policy.active_model.model_id == "gpt-e2e-large"
    assert policy.active_model.provider.base_url == ADDRESS
    assert policy.fallback_model is None


def test_the_owner_speaks_the_language_asked(seed):
    seed.panel(ADDRESS, "en")

    assert get_user_model().objects.get(email="e2e-assistant-owner@example.com").language == "en"


def test_clear_leaves_nothing_of_the_owner(seed):
    seed.panel(ADDRESS)
    owner = get_user_model().objects.get(email="e2e-assistant-owner@example.com")
    AssistantUsage.objects.create(user=owner, month=queries.month_of(timezone.now()), messages=2)

    seed.clear()

    assert not get_user_model().objects.filter(email="e2e-assistant-owner@example.com").exists()
    assert not Hub.objects.filter(slug="e2e-assistant-panel").exists()
    assert not HubMembership.objects.filter(hub_slug="e2e-assistant-panel").exists()
    assert not AssistantUsage.objects.filter(user__email="e2e-assistant-owner@example.com").exists()


def test_every_run_starts_from_scratch(seed):
    seed.panel(ADDRESS)
    seed.clear()
    seed.panel(ADDRESS)

    assert get_user_model().objects.filter(email="e2e-assistant-owner@example.com").count() == 1
    assert Hub.objects.filter(slug="e2e-assistant-panel").count() == 1


def _keyed(slug: str) -> None:
    from assistant.models import AIProvider, AIProviderCredential

    provider = AIProvider.objects.create(slug=slug, name=slug.title(), kind="openai", base_url="https://example.com/v1")
    AIProviderCredential.objects.create(
        provider=provider, label="default", api_key=f"sk-{slug}-0000000000000000", key_hint="0000"
    )


def test_forget_takes_the_real_keys_away_and_keeps_the_others(seed):
    from assistant.models import AIProviderCredential

    for slug in ("qwen", "openai", "mistral"):
        _keyed(slug)

    seed.forget()

    assert list(AIProviderCredential.objects.values_list("provider__slug", flat=True)) == ["mistral"]


def test_forget_and_real_refuse_any_database_but_the_run_s_own_e2e_one(seed):
    # pytest's own database is no e2e one; the shared ``saas`` of a developer is refused the same way.
    with pytest.raises(SystemExit, match="forget: only on the run's own e2e database"):
        seed.e2e_only("forget")
    with pytest.raises(SystemExit, match="real: .* never on 'saas'"):
        seed.e2e_only("real", "saas")
    seed.e2e_only("forget", "saas_e2e_8630")
    seed.e2e_only("real", "saas_e2e_qa2")


def _named(settings, name: str) -> None:
    """The configured database named ``name`` for the seed's guard (the test's connection is not touched)."""
    settings.DEBUG = True
    settings.DATABASES = {**settings.DATABASES, "default": {**settings.DATABASES["default"], "NAME": name}}


def _left() -> tuple[list[str], list[str], list[str]]:
    from assistant.models import AIProviderCredential

    return (
        sorted(get_user_model().objects.filter(email__startswith="e2e-assistant-").values_list("email", flat=True)),
        sorted(Hub.objects.filter(slug__startswith="e2e-assistant-").values_list("slug", flat=True)),
        sorted(AIProviderCredential.objects.values_list("provider__slug", flat=True)),
    )


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
@pytest.mark.parametrize("action", ["forget", "real"])
def test_main_refuses_the_shared_database_and_deletes_nothing(seed, settings, action):
    seed.panel(ADDRESS)
    for slug in ("qwen", "openai"):
        _keyed(slug)
    before = _left()
    _named(settings, "saas")

    with pytest.raises(SystemExit, match=f"{action}: only on the run's own e2e database .* never on 'saas'"):
        seed.main(action, "", "es")

    assert _left() == before
    assert before[0] and before[1]


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
def test_main_forget_on_an_e2e_database_removes_the_qa_accounts_their_businesses_and_the_real_keys(seed, settings):
    seed.panel(ADDRESS)
    for slug in ("qwen", "openai", "mistral"):
        _keyed(slug)
    _named(settings, "saas_e2e_8630")

    seed.main("forget", "", "es")

    assert _left() == ([], [], ["mistral"])
