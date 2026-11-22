"""The rows of the AI gateway: provider, model and policy.

- A provider is one of the four APIs our clients speak (``kind``), with its own address only over https (the key
  travels to it); a local address is for the tests and a provider of our own on the same machine.
- A provider's key lives in the environment only: the provider names the variable it reads (several providers speak
  OpenAI's API, each with its own key), and one whose variable is empty has no key. Nothing else of the environment
  can be read through it, and the key never shows in its name.
"""

import pytest
from django.core.exceptions import ValidationError

from assistant.models import KEY_VARIABLES, AIProvider
from assistant.tests.conftest import API_KEY

pytestmark = pytest.mark.django_db


# --- AIProvider ------------------------------------------------------------------------------------------


def test_the_kinds_are_the_four_apis_of_models():
    assert set(AIProvider.Kind.values) == {"openai", "anthropic", "gemini", "deepseek"}


@pytest.mark.parametrize(
    "base_url",
    ["", "https://api.openai.com/v1", "https://proxy.example.com/openai", "http://127.0.0.1:8949/v1", "http://localhost:9000"],
)
def test_an_address_over_https_or_on_this_machine_is_accepted(base_url):
    AIProvider(slug="custom", name="Custom", kind="openai", base_url=base_url, key_variable="OPENAI_API_KEY").full_clean()


@pytest.mark.parametrize("base_url", ["http://api.openai.com/v1", "http://10.0.0.5/v1", "ftp://example.com"])
def test_an_address_where_the_key_would_travel_in_the_clear_is_refused(base_url):
    with pytest.raises(ValidationError) as refused:
        AIProvider(slug="custom", name="Custom", kind="openai", base_url=base_url, key_variable="OPENAI_API_KEY").full_clean()

    assert "base_url" in refused.value.message_dict


def test_the_default_address_comes_from_the_kind():
    assert AIProvider(kind="openai").api_base == "https://api.openai.com/v1"
    assert AIProvider(kind="anthropic").api_base == "https://api.anthropic.com"
    assert AIProvider(kind="gemini").api_base == "https://generativelanguage.googleapis.com"
    assert AIProvider(kind="deepseek").api_base == "https://api.deepseek.com"
    assert AIProvider(kind="openai", base_url="https://proxy.example.com/v1/").api_base == "https://proxy.example.com/v1"


def test_a_provider_is_named_by_its_name():
    assert str(AIProvider(slug="openai", name="OpenAI", kind="openai")) == "OpenAI"


# --- A provider's key, from the environment ------------------------------------------------------------


def test_the_variables_a_provider_may_read_are_the_ai_keys_of_the_environment():
    assert KEY_VARIABLES == ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY")
    assert [name for name, _ in AIProvider._meta.get_field("key_variable").choices] == list(KEY_VARIABLES)


def test_a_provider_must_name_the_variable_of_its_key():
    with pytest.raises(ValidationError) as refused:
        AIProvider(slug="custom", name="Custom", kind="openai").full_clean()

    assert "key_variable" in refused.value.message_dict


def test_a_provider_reads_its_key_from_the_variable_it_names(settings):
    settings.OPENAI_API_KEY = API_KEY
    settings.DASHSCOPE_API_KEY = "sk-qwen-0000000000000000000000000000qwen"
    openai = AIProvider(kind="openai", key_variable="OPENAI_API_KEY")
    qwen = AIProvider(kind="openai", base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1", key_variable="DASHSCOPE_API_KEY")

    assert (openai.api_key, openai.has_key) == (API_KEY, True)
    assert (qwen.api_key, qwen.has_key) == ("sk-qwen-0000000000000000000000000000qwen", True)


def test_a_new_key_in_the_environment_is_read_on_the_next_call(settings):
    provider = AIProvider(kind="openai", key_variable="OPENAI_API_KEY")
    assert (provider.api_key, provider.has_key) == ("", False)

    settings.OPENAI_API_KEY = f"  {API_KEY}\n"
    assert provider.api_key == API_KEY


def test_a_provider_naming_no_variable_has_no_key(settings):
    settings.OPENAI_API_KEY = API_KEY

    assert (AIProvider(kind="openai").api_key, AIProvider(kind="openai").has_key) == ("", False)


@pytest.mark.parametrize("variable", ["SECRET_KEY", "FERNET_KEY", "DATABASES", "openai_api_key"])
def test_a_variable_that_is_no_ai_key_is_never_read(settings, variable):
    """The choices are the form's; a row written around them still reads nothing else of the environment."""
    settings.OPENAI_API_KEY = API_KEY

    assert AIProvider(kind="openai", key_variable=variable).api_key == ""


def test_a_provider_never_shows_its_key(settings):
    settings.OPENAI_API_KEY = API_KEY
    provider = AIProvider(slug="openai", name="OpenAI", kind="openai", key_variable="OPENAI_API_KEY")

    for shown in (str(provider), repr(provider)):
        assert API_KEY not in shown and API_KEY[-4:] not in shown


def test_no_row_of_the_gateway_keeps_a_key():
    from django.apps import apps

    columns = {f"{model._meta.label}.{field.name}" for model in apps.get_app_config("assistant").get_models() for field in model._meta.concrete_fields}

    assert {column for column in columns if "key" in column.rsplit(".", 1)[1]} == {"assistant.AIProvider.key_variable"}


def test_the_keys_of_the_environment_are_no_longer_copied_into_the_database():
    from django.core.management import CommandError, call_command

    with pytest.raises(CommandError, match="Unknown command"):
        call_command("import_ai_keys_from_env")


# --- AIModel --------------------------------------------------------------------------------------------


def test_a_model_is_named_with_its_provider(provider):
    from assistant.models import AIModel

    model = AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")

    assert str(model) == "GPT-5.5 (openai)"
    assert (model.is_available, model.supports_tools, model.supports_vision, model.context_window) == (True, True, False, 0)


def test_the_cost_of_a_turn_is_exact_money(provider):
    from decimal import Decimal

    from assistant.models import AIModel

    model = AIModel(provider=provider, model_id="m", price_input_per_1m=Decimal("5.0000"), price_output_per_1m=Decimal("30.0000"))

    assert model.estimate_cost(1_200, 300) == Decimal("0.015")
    assert isinstance(model.estimate_cost(1, 1), Decimal)


def test_a_provider_cannot_list_one_model_twice(provider):
    from assistant.models import AIModel

    AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")

    with pytest.raises(ValidationError):
        AIModel(provider=provider, model_id="gpt-5.5", display_name="again").validate_constraints()


# --- AIRoutingPolicy ------------------------------------------------------------------------------------


def test_there_is_one_policy_and_a_model_it_uses_cannot_be_deleted(provider):
    from django.db.models import ProtectedError

    from assistant.models import AIModel, AIRoutingPolicy

    model = AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")
    policy = AIRoutingPolicy.solo()
    policy.active_model = model
    policy.save()

    assert AIRoutingPolicy.solo().pk == policy.pk
    assert AIRoutingPolicy.objects.count() == 1
    with pytest.raises(ProtectedError):
        model.delete()


def test_a_policy_says_which_models_answer(provider):
    from assistant.models import AIModel, AIRoutingPolicy

    active = AIModel.objects.create(provider=provider, model_id="a", display_name="Active")
    fallback = AIModel.objects.create(provider=provider, model_id="b", display_name="Fallback")

    assert str(AIRoutingPolicy(active_model=active, fallback_model=fallback)) == "Active (openai) → Fallback (openai)"
    assert str(AIRoutingPolicy()) == "—"
