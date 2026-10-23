"""«Try a model» in the admin (ASSISTANT-G61; old SAAS_ASSISTANT-F24): the staff who may change the model that answers
send one message to one model and watch its answer arrive, with its tokens, its time and its cost, before choosing it.

The page is a form of the admin; the run is an asynchronous view that streams server-sent events (the provider's call
never holds a thread other requests need). The provider is ``fake_provider``, a real HTTP server on ``127.0.0.1``. A
run touches no business, quota nor conversation; it stays in the audit trail without the message.
"""

import json

import pytest
from asgiref.sync import async_to_sync
from auditlog.models import LogEntry
from live.models import OutboxEvent

from assistant.models import AIModel, AIProvider, AIProviderCredential
from assistant.tests.conftest import API_KEY, grant
from assistant.tests.fake_provider import openai_chunk

pytestmark = pytest.mark.django_db

POLICY = "/admin/assistant/airoutingpolicy/policy/"
TRY = "/admin/assistant/airoutingpolicy/policy/try/"
RUN = "/admin/assistant/airoutingpolicy/policy/try/run/"
PROMPT = "Write the receipt of a coffee for table four"


@pytest.fixture
def tried(fake_provider):
    """An OpenAI-compatible provider at the fake server, with a key and one model at 1 / 2 USD per million tokens."""
    provider = AIProvider.objects.create(slug="local", name="Local", kind="openai", base_url=f"{fake_provider.url}/v1")
    AIProviderCredential.objects.create(provider=provider, label="default", api_key=API_KEY, key_hint="wxyz")
    return AIModel.objects.create(
        provider=provider,
        model_id="gpt-e2e-large",
        display_name="Large",
        price_input_per_1m="1",
        price_output_per_1m="2",
    )


@pytest.fixture
def as_ai_admin(client, ai_admin):
    client.force_login(ai_admin)
    return client


def answer(text: str, tokens_in: int = 1200, tokens_out: int = 300) -> list:
    return [
        openai_chunk(text, finish="stop"),
        openai_chunk(usage={"prompt_tokens": tokens_in, "completion_tokens": tokens_out}),
        "[DONE]",
    ]


async def _collect(content) -> bytes:
    return b"".join([chunk async for chunk in content])


def events(response) -> list[dict]:
    """The server-sent events of a run, in order."""
    assert response.status_code == 200 and response["Content-Type"] == "text/event-stream"
    body = async_to_sync(_collect)(response.streaming_content).decode()
    return [json.loads(block.removeprefix("data: ")) for block in body.split("\n\n") if block.strip()]


def run(client, model, prompt=PROMPT, **extra):
    return client.post(RUN, {"model": str(model.pk) if hasattr(model, "pk") else model, "prompt": prompt, **extra})


# --- The page ------------------------------------------------------------------------------------------------


def test_the_page_of_the_model_that_answers_leads_to_trying_a_model(as_ai_admin):
    page = as_ai_admin.get(POLICY).content.decode()

    # Once: the admin paints the block of the page's tools in its own place (a second copy inside the page doubled it).
    assert page.count(f'href="{TRY}"') == 1 and "Try a model" in page


def test_who_may_only_look_at_the_policy_is_not_led_to_try_a_model(client, make_user):
    client.force_login(grant(make_user("viewer@erplora.com", is_staff=True), "view_airoutingpolicy"))

    assert f'href="{TRY}"' not in client.get(POLICY).content.decode()


def test_the_page_offers_the_models_that_can_answer_and_a_message(as_ai_admin, tried):
    AIModel.objects.create(provider=tried.provider, model_id="gpt-off", display_name="Off", is_available=False)

    response = as_ai_admin.get(TRY)

    page = response.content.decode()
    assert response.status_code == 200
    assert f'<option value="{tried.pk}">Local · Large (gpt-e2e-large)</option>' in page
    assert "gpt-off" not in page
    assert '<textarea name="prompt"' in page and '<textarea name="tools"' in page
    assert f'data-run-url="{RUN}"' in page
    # The page's script carries the nonce of the response's policy (CSP with strict-dynamic and Trusted Types).
    nonce = response.context["csp_nonce"]
    assert f'<script nonce="{nonce}">' in page and "innerHTML" not in page


def test_the_page_says_so_when_no_model_can_be_tried(as_ai_admin):
    page = as_ai_admin.get(TRY).content.decode()

    assert "No model can answer yet: add a provider with its key and choose its models." in page


def test_the_page_is_in_spanish_for_the_staff_who_read_spanish(as_ai_admin, tried):
    page = as_ai_admin.get(TRY, headers={"accept-language": "es"}).content.decode()

    assert "Probar un modelo" in page and "Enviar" in page


@pytest.mark.parametrize("path", [TRY, RUN])
def test_who_is_not_in_the_admin_goes_to_sign_in(client, path):
    response = client.get(path) if path == TRY else client.post(path, {"prompt": PROMPT})

    assert response.status_code == 302 and response["Location"].startswith("/admin/login/")


@pytest.mark.parametrize("codenames", [(), ("view_airoutingpolicy",)])
@pytest.mark.parametrize("path", [TRY, RUN])
def test_the_staff_without_permission_to_change_the_model_that_answers_cannot_try_one(client, make_user, tried, fake_provider, path, codenames):
    client.force_login(grant(make_user("member@erplora.com", is_staff=True), *codenames))

    response = client.get(path) if path == TRY else run(client, tried)

    assert response.status_code == 403
    assert fake_provider.requests == []


# --- The run -------------------------------------------------------------------------------------------------


def test_a_run_streams_the_answer_with_its_tokens_time_and_cost(as_ai_admin, tried, fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=answer("A coffee, 1.50 €."))

    seen = events(run(as_ai_admin, tried))

    assert [event["type"] for event in seen] == ["model", "text_delta", "usage", "finish", "metrics", "done"]
    assert seen[0] == {"type": "model", "model": str(tried.pk), "model_id": "gpt-e2e-large", "display_name": "Large", "provider": "Local"}
    assert seen[1] == {"type": "text_delta", "text": "A coffee, 1.50 €."}
    metrics = seen[4]
    assert (metrics["input_tokens"], metrics["output_tokens"]) == (1200, 300)
    # (1200 × 1 + 300 × 2) / 1 000 000 USD, exact.
    assert metrics["cost_usd"] == "0.0018"
    assert isinstance(metrics["latency_ms"], int) and metrics["latency_ms"] >= 0
    [request] = fake_provider.requests
    assert request.body["model"] == "gpt-e2e-large"
    assert request.body["messages"][-1] == {"role": "user", "content": PROMPT}


def test_a_run_never_shows_the_key(as_ai_admin, tried, fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", status=401, json={"error": {"message": f"Bad key {API_KEY}"}})

    seen = events(run(as_ai_admin, tried))

    assert API_KEY not in json.dumps(seen)
    assert [event["type"] for event in seen] == ["model", "error", "finish", "metrics", "done"]
    assert seen[1]["message"] == "openai: Bad key …"


def test_the_tools_typed_are_offered_to_the_model(as_ai_admin, tried, fake_provider):
    fake_provider.reply(
        "POST",
        "/v1/chat/completions",
        sse=[
            openai_chunk(tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "create_invoice", "arguments": '{"table": 4}'}}]),
            openai_chunk(finish="tool_calls"),
            "[DONE]",
        ],
    )
    tools = [{"name": "create_invoice", "description": "Issue a receipt", "parameters": {"type": "object", "properties": {"table": {"type": "integer"}}}}]

    seen = events(run(as_ai_admin, tried, tools=json.dumps(tools)))

    [request] = fake_provider.requests
    assert [tool["function"]["name"] for tool in request.body["tools"]] == ["create_invoice"]
    assert {"type": "tool_call", "call_id": "call_1", "name": "create_invoice", "arguments": '{"table": 4}'} in seen


@pytest.mark.parametrize(
    ("tools", "message"),
    [
        ("[{", "The tools are not well written: write a list of tools as in the example, each with its name."),
        ('{"name": "x"}', "The tools are not well written: write a list of tools as in the example, each with its name."),
        ('[{"description": "no name"}]', "The tools are not well written: write a list of tools as in the example, each with its name."),
    ],
)
def test_tools_that_are_not_a_list_of_named_tools_are_refused_before_calling(as_ai_admin, tried, fake_provider, tools, message):
    seen = events(run(as_ai_admin, tried, tools=tools))

    assert seen == [{"type": "error", "message": message}, {"type": "done"}]
    assert fake_provider.requests == []
    assert not LogEntry.objects.filter(action=LogEntry.Action.ACCESS).exists()


def test_a_run_without_a_message_is_refused_before_calling(as_ai_admin, tried, fake_provider):
    seen = events(run(as_ai_admin, tried, prompt="   "))

    assert seen == [{"type": "error", "message": "Write the message to send."}, {"type": "done"}]
    assert fake_provider.requests == []


def test_a_model_that_cannot_answer_says_why_in_the_language_of_the_staff(as_ai_admin, tried, fake_provider):
    tried.is_available = False
    tried.save()

    seen = events(as_ai_admin.post(RUN, {"model": str(tried.pk), "prompt": PROMPT}, headers={"accept-language": "es"}))

    assert seen == [
        {"type": "error", "message": "Este modelo está apagado o lo está su proveedor: enciéndelos para usarlo."},
        {"type": "done"},
    ]
    assert fake_provider.requests == []


@pytest.mark.parametrize("model", ["", "not-a-model"])
def test_a_run_without_a_model_of_the_list_is_refused(as_ai_admin, tried, fake_provider, model):
    seen = events(run(as_ai_admin, model))

    assert seen == [{"type": "error", "message": "Choose the model to try from the list."}, {"type": "done"}]
    assert fake_provider.requests == []


def test_a_model_whose_provider_has_no_key_says_so(as_ai_admin, tried, fake_provider):
    AIProviderCredential.objects.update(is_active=False)

    seen = events(run(as_ai_admin, tried))

    assert seen[0] == {
        "type": "error",
        "message": "No model can answer: the providers of the chosen models have no active key.",
    }
    assert fake_provider.requests == []


def test_too_many_runs_in_a_minute_are_refused(as_ai_admin, tried, fake_provider, settings):
    settings.ASSISTANT_TRY_RATELIMIT = "2/m"
    fake_provider.reply("POST", "/v1/chat/completions", always=True, sse=answer("Hi"))
    for _ in range(2):
        assert events(run(as_ai_admin, tried))[-1] == {"type": "done"}

    refused = run(as_ai_admin, tried)

    assert refused.status_code == 429
    assert refused.content.decode() == "Too many tries in a minute: wait a moment and try again."
    assert len(fake_provider.requests) == 2


def test_a_run_stays_in_the_audit_trail_without_the_message(as_ai_admin, ai_admin, tried, fake_provider):
    fake_provider.reply("POST", "/v1/chat/completions", sse=answer("Hi"))

    events(run(as_ai_admin, tried, tools=json.dumps([{"name": "create_invoice"}])))

    [entry] = LogEntry.objects.filter(action=LogEntry.Action.ACCESS)
    assert (entry.content_type.model, entry.object_pk, entry.actor_id) == ("aimodel", str(tried.pk), ai_admin.pk)
    assert entry.additional_data == {"tried": True, "prompt_chars": len(PROMPT), "tools": 1}
    assert PROMPT not in json.dumps([entry.additional_data, entry.changes, entry.serialized_data], default=str)
    [event] = OutboxEvent.objects.filter(name="assistant.model.tried")
    assert event.payload == {"model": str(tried.pk), "prompt_chars": len(PROMPT), "tools": 1}


# --- The gateway's own pages look like the rest of the admin -----------------------------------------------------


@pytest.mark.parametrize("page_of", ["policy", "try", "models"])
def test_the_gateways_own_pages_carry_the_admins_breadcrumbs_and_form_styles(as_ai_admin, provider, page_of):
    """Django 6.1 styles its breadcrumbs as a list and its aligned forms with ``forms.css``: a page of our own that
    kept the older ``<div>`` showed a bare line of links, and its fields out of line."""
    path = {"policy": POLICY, "try": TRY, "models": f"/admin/assistant/aiprovider/{provider.pk}/models/"}[page_of]

    page = as_ai_admin.get(path).content.decode()

    assert '<ol class="breadcrumbs">' in page and '<div class="breadcrumbs">' not in page
    assert "/static/admin/css/forms.css" in page


def test_the_last_change_of_the_model_that_answers_reads_as_one_sentence(as_ai_admin, ai_admin, provider):
    from assistant import services
    from assistant.schemas import PolicyIn
    from assistant.tests.conftest import staff_ctx

    model = AIModel.objects.create(provider=provider, model_id="gpt-5.5", display_name="GPT-5.5")
    services.policy_update(staff_ctx(ai_admin), PolicyIn(active_model=model.pk))

    page = as_ai_admin.get(POLICY).content.decode()

    assert "Last changed by ai-admin@erplora.com on " in page and ".." not in page
