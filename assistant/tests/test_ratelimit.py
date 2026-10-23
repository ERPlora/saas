"""ASSISTANT-F16 (ASSISTANT-G48) · Stop a business that asks too much: each door has a budget per business (or demo)
in Django's cache (Valkey in production; no Redis for anything live), spent only once the signature and the business
passed (saas#2531). Over it, 429 ``rate_limited`` with ``Retry-After``: a code apart from the spent allowance
(``assistant.quota_exceeded``), as the providers' APIs separate them (SAAS_ASSISTANT-F07/F08 of the old product).
"""

import pytest
from django.test import Client

from assistant.tests.conftest import openai_answer
from assistant.tests.doors import door, error_code, frames

USAGE = "/internal/assistant/usage"
STREAM = "/internal/assistant/chat/stream"

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


def test_over_its_budget_a_business_waits_and_is_told_how_long(client, internal, business, settings):
    settings.ASSISTANT_TURN_RATELIMIT = "2/h"

    answers = [door(client, USAGE, {"hub": business.slug}) for _ in range(3)]

    assert [answer.status_code for answer in answers] == [200, 200, 429]
    assert error_code(answers[2]) == "rate_limited"
    assert 0 < int(answers[2]["Retry-After"]) <= 3600


def test_the_turn_over_its_budget_never_reaches_the_model(client, internal, business, settings, answering, fake_provider):
    settings.ASSISTANT_TURN_RATELIMIT = "1/h"
    fake_provider.reply("POST", "/v1/chat/completions", sse=openai_answer("Ok"), always=True)
    frames(door(client, STREAM, {"hub": business.slug, "messages": [{"role": "user", "content": "Hi"}]}))

    response = door(client, STREAM, {"hub": business.slug, "messages": [{"role": "user", "content": "Hi"}]})

    assert (response.status_code, error_code(response)) == (429, "rate_limited")
    assert len([seen for seen in fake_provider.requests if seen.path.endswith("/chat/completions")]) == 1


def test_the_budget_is_each_businesss_own(client, internal, business, settings, make_user):
    from hubs.models import Hub
    from hubs.tests.conftest import create_business

    settings.ASSISTANT_TURN_RATELIMIT = "1/h"
    other = create_business(make_user("pepe@example.com"), name="Bar Pepe")
    Hub.objects.filter(pk=other.pk).update(status=Hub.Status.ACTIVE)
    door(client, USAGE, {"hub": business.slug})

    assert door(client, USAGE, {"hub": business.slug}).status_code == 429
    assert door(client, USAGE, {"hub": other.slug}).status_code == 200


def test_a_business_named_by_its_id_spends_the_same_budget(client, internal, business, settings):
    settings.ASSISTANT_TURN_RATELIMIT = "1/h"
    door(client, USAGE, {"hub": business.slug})

    assert door(client, USAGE, {"hub": str(business.id)}).status_code == 429


def test_each_demo_has_its_own_budget(client, internal, settings):
    settings.ASSISTANT_TURN_RATELIMIT = "1/h"
    door(client, USAGE, {"hub": "demo-1a2b3c4d"})

    assert door(client, USAGE, {"hub": "demo-1a2b3c4d"}).status_code == 429
    assert door(client, USAGE, {"hub": "demo-ffffffff"}).status_code == 200


def test_an_unknown_business_spends_no_budget_of_anyone(client, internal, business, settings):
    settings.ASSISTANT_TURN_RATELIMIT = "1/h"
    for _ in range(3):
        door(client, USAGE, {"hub": "nobody-here"})

    assert door(client, USAGE, {"hub": business.slug}).status_code == 200
