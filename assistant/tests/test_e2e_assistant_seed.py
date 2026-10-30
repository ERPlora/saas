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
