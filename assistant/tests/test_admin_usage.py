"""ASSISTANT-F24 (ASSISTANT-G52, G19, G11) · See what a business spent of the assistant and what it cost: the
admin's «Assistant usage» (``erplora.com/admin/assistant/assistantusage/``), a row per business and month (a demo,
one for its whole life) with its messages of the plan's allowance, the tokens of its turns and of its embeddings, its
dictations, the characters read aloud and the cost in USD (with the prices of the model that answered each turn).

Read only, for everybody, a superuser included: the old page let the staff edit the tokens, add rows and delete them,
and deleting this month's row gave a business its whole allowance back (SAAS_ASSISTANT-F15). Only staff with the
permission to see it enter. Cases of the old ``AssistantUsageAdmin`` and its gaps.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from assistant import queries
from assistant.models import AssistantUsage
from assistant.tests.conftest import grant

pytestmark = pytest.mark.django_db

USAGE = "/admin/assistant/assistantusage/"


@pytest.fixture
def rows(business):
    month = queries.month_of(timezone.now())
    spent = AssistantUsage.objects.create(
        hub=business,
        month=month,
        messages=12,
        tokens_input=34_000,
        tokens_output=5_600,
        tokens_embedding=900,
        transcriptions=3,
        speech_characters=420,
        cost_usd=Decimal("0.113"),
    )
    demo = AssistantUsage.objects.create(demo="demo-1a2b3c4d", month=month, messages=7)
    return spent, demo


@pytest.fixture
def viewer(make_user):
    return grant(make_user("finance@erplora.com", first_name="Fina", is_staff=True), "view_assistantusage")


def test_the_staff_see_each_businesss_spending_and_its_cost(client, viewer, rows, business):
    client.force_login(viewer)

    response = client.get(USAGE)

    assert response.status_code == 200
    page = response.content.decode()
    assert business.name in page and "demo-1a2b3c4d" in page
    for figure in ("34000", "5600", "900", "420", "0.113"):
        assert figure in page.replace(",", "").replace(".", ".")


def test_a_business_is_found_by_its_name_or_address(client, viewer, rows, business):
    client.force_login(viewer)

    by_name = client.get(USAGE, {"q": business.name}).content.decode()
    by_demo = client.get(USAGE, {"q": "demo-1a2b"}).content.decode()

    assert business.name in by_name and "demo-1a2b3c4d" not in by_name
    assert "demo-1a2b3c4d" in by_demo and business.name not in by_demo


def test_the_demos_and_the_businesses_are_told_apart(client, viewer, rows, business):
    client.force_login(viewer)

    demos = client.get(USAGE, {"kind": "demo"}).content.decode()

    assert "demo-1a2b3c4d" in demos and business.name not in demos


def test_nobody_adds_changes_or_deletes_a_row_not_even_a_superuser(client, make_user, rows):
    spent, _ = rows
    boss = make_user("boss@erplora.com", is_staff=True, is_superuser=True)
    client.force_login(boss)

    assert client.get(f"{USAGE}add/").status_code == 403
    assert client.post(f"{USAGE}{spent.pk}/delete/", {"post": "yes"}).status_code == 403
    client.post(f"{USAGE}{spent.pk}/change/", {"messages": "0"})
    assert AssistantUsage.objects.get(pk=spent.pk).messages == 12
    page = client.get(f"{USAGE}{spent.pk}/change/").content.decode()
    assert 'name="messages"' not in page
    assert "12" in page


def test_staff_without_the_permission_do_not_enter(client, plain_staff, rows):
    client.force_login(plain_staff)

    assert client.get(USAGE).status_code == 403


def test_it_reads_in_spanish(client, viewer, rows):
    client.force_login(viewer)

    page = client.get(USAGE, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert "Uso del asistente" in page
    assert "Coste (USD)" in page
