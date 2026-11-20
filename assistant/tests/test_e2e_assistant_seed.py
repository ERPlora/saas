"""ASSISTANT-F25 · The rows the panel's assistant's e2e opens (``tests/e2e/panel/assistant_seed.py panel``, the one
``panel/assistant-panel.spec.ts`` runs): the e2e's model answering, at the address of the spec's own provider, and
``e2e-assistant-owner``, an account like any other (no staff) with one working business, in the language the spec
asks for. ``clear`` leaves nothing of it behind: the account, its business, its access and its month's messages.
"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from assistant import queries
from assistant.models import AIProvider, AIRoutingPolicy, AssistantUsage
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
def seed(monkeypatch, plans):  # noqa: F811 - the fixture above
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


def test_the_e2e_model_answers_at_the_spec_provider(seed):
    seed.panel(ADDRESS)

    policy = AIRoutingPolicy.solo()
    assert policy.active_model.model_id == "gpt-e2e-large"
    assert policy.active_model.provider.base_url == ADDRESS
    assert policy.active_model.provider.key_variable == "OPENAI_API_KEY"
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
    assert not AssistantUsage.objects.filter(user__email="e2e-assistant-owner@example.com").exists()


def test_every_run_starts_from_scratch(seed):
    seed.panel(ADDRESS)
    seed.clear()
    seed.panel(ADDRESS)

    assert get_user_model().objects.filter(email="e2e-assistant-owner@example.com").count() == 1
    assert Hub.objects.filter(slug="e2e-assistant-panel").count() == 1





def test_paying_runs_again_from_scratch(seed):
    seed.paying(ADDRESS)
    seed.clear()
    seed.paying(ADDRESS)

    assert Hub.objects.filter(slug="e2e-assistant-panel").count() == 1


def test_real_refuses_any_database_but_the_run_s_own_e2e_one(seed):
    # pytest's own database is no e2e one; the shared ``saas`` of a developer is refused the same way.
    with pytest.raises(SystemExit, match="real: only on the run's own e2e database"):
        seed.e2e_only("real")
    with pytest.raises(SystemExit, match="real: .* never on 'saas'"):
        seed.e2e_only("real", "saas")
    seed.e2e_only("real", "saas_e2e_qa2")


def test_no_action_keeps_or_forgets_a_key_any_more(seed, settings):
    """The keys live in the environment of the run's servers: the seed never writes one, so nothing is left to
    forget after a run."""
    settings.DEBUG = True
    with pytest.raises(SystemExit, match="unknown action 'forget'"):
        seed.main("forget", "", "es")


def _named(settings, name: str) -> None:
    """The configured database named ``name`` for the seed's guard (the test's connection is not touched)."""
    settings.DEBUG = True
    settings.DATABASES = {**settings.DATABASES, "default": {**settings.DATABASES["default"], "NAME": name}}


def _left() -> tuple[list[str], list[str], list[tuple[str, str]]]:
    return (
        sorted(get_user_model().objects.filter(email__startswith="e2e-assistant-").values_list("email", flat=True)),
        sorted(Hub.objects.filter(slug__startswith="e2e-assistant-").values_list("slug", flat=True)),
        sorted(AIProvider.objects.values_list("slug", "base_url")),
    )


@pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")
def test_main_real_refuses_the_shared_database_and_changes_nothing(seed, settings, monkeypatch):
    seed.panel(ADDRESS)
    AIProvider.objects.create(slug="qwen", name="Qwen (mine)", kind="openai", base_url="https://mine.example.com/v1", key_variable="DASHSCOPE_API_KEY")
    for name, value in KEYS.items():
        monkeypatch.setenv(name, value)
    before = _left()
    _named(settings, "saas")

    with pytest.raises(SystemExit, match="real: only on the run's own e2e database .* never on 'saas'"):
        seed.main("real", "", "es")

    assert _left() == before
    assert before[0] and before[1]


#: The keys a QA runner exports for ``real``: the servers of the run read them, the seed only checks they are there.
KEYS = {"DASHSCOPE_API_KEY": "sk-qwen-0000000000000000", "OPENAI_API_KEY": "sk-openai-0000000000000000"}
COMPARED = {
    "QA_ANSWER_KIND": "anthropic",
    "QA_ANSWER_MODEL": "claude-test-model",
    "QA_ANSWER_BASE_URL": "https://models.example.com/v1",
    "QA_ANSWER_KEY_ENV": "ANTHROPIC_API_KEY",
    "QA_ANSWER_PRICE_IN": "0.4",
    "QA_ANSWER_PRICE_OUT": "1.2",
}


def test_real_answers_with_qwen_and_its_openai_fallback_without_any_qa_answer_variable(seed):
    made = seed.real(seed.answer_choice({}))

    policy = AIRoutingPolicy.solo()
    assert (policy.active_model.provider.slug, policy.active_model.model_id) == ("qwen", "qwen3.7-plus")
    assert policy.active_model.provider.base_url == seed.QWEN["base_url"]
    assert policy.active_model.provider.key_variable == "DASHSCOPE_API_KEY"
    assert (policy.fallback_model.provider.slug, policy.fallback_model.model_id) == ("openai", "gpt-5.4-mini")
    assert (policy.fallback_model.provider.base_url, policy.fallback_model.provider.key_variable) == ("", "OPENAI_API_KEY")
    assert policy.active_model.price_input_per_1m == Decimal("0")
    assert (made["model"], made["fallback"]) == ("qwen3.7-plus (Qwen)", "gpt-5.4-mini (OpenAI)")
    assert made["answer"] == {
        "provider": "qwen",
        "kind": "openai",
        "model": "qwen3.7-plus",
        "base_url": seed.QWEN["base_url"],
        "price_in": None,
        "price_out": None,
        "fallback": "gpt-5.4-mini",
    }


def test_real_answers_with_the_model_under_test_alone_at_its_address_and_prices(seed):
    made = seed.real(seed.answer_choice(COMPARED))

    policy = AIRoutingPolicy.solo()
    answering = policy.active_model
    assert (answering.provider.slug, answering.provider.kind, answering.model_id) == ("qa-answer", "anthropic", "claude-test-model")
    assert answering.provider.base_url == "https://models.example.com/v1"
    assert answering.provider.key_variable == "ANTHROPIC_API_KEY"
    assert (answering.price_input_per_1m, answering.price_output_per_1m) == (Decimal("0.4"), Decimal("1.2"))
    assert policy.fallback_model is None
    assert made["fallback"] == "none"
    assert made["answer"]["fallback"] is None
    assert (made["answer"]["price_in"], made["answer"]["price_out"]) == (0.4, 1.2)


def test_real_refuses_an_address_the_admin_would_refuse(seed):
    with pytest.raises(Exception, match="https"):
        seed.real(seed.answer_choice({**COMPARED, "QA_ANSWER_BASE_URL": "http://models.example.com/v1"}))


def test_a_model_under_test_names_every_variable_it_lacks(seed):
    with pytest.raises(SystemExit, match="QA_ANSWER_KIND, QA_ANSWER_KEY_ENV, QA_ANSWER_PRICE_IN, QA_ANSWER_PRICE_OUT"):
        seed.answer_choice({"QA_ANSWER_MODEL": "m"})


def test_the_qa_answer_variables_without_a_model_are_refused_instead_of_answering_with_qwen(seed):
    with pytest.raises(SystemExit, match="QA_ANSWER_KIND without QA_ANSWER_MODEL"):
        seed.answer_choice({"QA_ANSWER_KIND": "openai"})


@pytest.mark.parametrize(
    ("name", "value", "said"),
    [
        ("QA_ANSWER_KIND", "mistral", "openai, anthropic, gemini, deepseek"),
        ("QA_ANSWER_PRICE_IN", "cheap", "QA_ANSWER_PRICE_IN"),
        ("QA_ANSWER_PRICE_OUT", "-1", "QA_ANSWER_PRICE_OUT"),
        ("QA_ANSWER_KEY_ENV", "sk-a-real-key", "QA_ANSWER_KEY_ENV"),
        ("QA_ANSWER_KEY_ENV", "QA_TEST_ANSWER_KEY", "OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, DASHSCOPE_API_KEY"),
    ],
)
def test_a_model_under_test_with_a_wrong_value_is_refused(seed, name, value, said):
    with pytest.raises(SystemExit, match=said):
        seed.answer_choice({**COMPARED, name: value})


@pytest.mark.parametrize(
    ("environ", "missing"),
    [
        ({"OPENAI_API_KEY": "sk-openai"}, "DASHSCOPE_API_KEY"),
        ({"DASHSCOPE_API_KEY": "sk-qwen", "OPENAI_API_KEY": " "}, "OPENAI_API_KEY"),
    ],
)
def test_real_names_the_variable_of_a_key_the_run_lacks(seed, environ, missing):
    with pytest.raises(SystemExit, match=f"real: export {missing} "):
        seed.keys_exported(seed.answer_choice({}), environ)


def test_real_checks_the_variable_of_the_model_under_test_and_never_prints_a_key(seed, capsys):
    with pytest.raises(SystemExit, match="real: export ANTHROPIC_API_KEY ") as refused:
        seed.keys_exported(seed.answer_choice(COMPARED), KEYS)
    seed.keys_exported(seed.answer_choice(COMPARED), {**KEYS, "ANTHROPIC_API_KEY": "sk-ant-0000000000000000"})

    printed = str(refused.value) + "".join(capsys.readouterr())
    assert all(key not in printed for key in (*KEYS.values(), "sk-ant-0000000000000000"))
