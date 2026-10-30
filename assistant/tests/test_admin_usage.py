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

    assert "Registros de uso del asistente" in page
    assert "Coste (USD)" in page
    # The counter under the list speaks a plural (it said «2 uso del asistente»).
    assert "2 registros de uso del asistente" in page


def test_the_counter_under_the_list_is_a_plural(client, viewer, rows):
    client.force_login(viewer)

    assert "2 assistant usage records" in client.get(USAGE).content.decode()


# --- An account's own allowance of the panel's assistant (plan 2026-10-30, §4) ----------------------------------


@pytest.fixture
def account_row(make_user):
    account = make_user("ana.cuenta@example.com", first_name="Ana")
    return AssistantUsage.objects.create(user=account, month=queries.month_of(timezone.now()), messages=9)


def test_an_accounts_row_is_named_by_its_email(client, viewer, rows, account_row, business):
    client.force_login(viewer)

    page = client.get(USAGE).content.decode()

    assert "ana.cuenta@example.com" in page
    assert "3 assistant usage records" in page


def test_the_accounts_are_a_kind_of_their_own(client, viewer, rows, account_row, business):
    client.force_login(viewer)

    accounts = client.get(USAGE, {"kind": "account"}).content.decode()
    businesses = client.get(USAGE, {"kind": "business"}).content.decode()
    demos = client.get(USAGE, {"kind": "demo"}).content.decode()

    assert "ana.cuenta@example.com" in accounts
    assert business.name not in accounts and "demo-1a2b3c4d" not in accounts
    assert "ana.cuenta@example.com" not in businesses and "ana.cuenta@example.com" not in demos
    assert ">Accounts<" in accounts


def test_an_account_is_found_by_its_email(client, viewer, rows, account_row, business):
    client.force_login(viewer)

    found = client.get(USAGE, {"q": "ana.cuenta"}).content.decode()

    assert "ana.cuenta@example.com" in found and business.name not in found


def test_the_accounts_read_in_spanish(client, viewer, rows, account_row):
    client.force_login(viewer)

    page = client.get(USAGE, HTTP_ACCEPT_LANGUAGE="es").content.decode()

    assert ">Cuentas<" in page
    assert "Negocio, demo o cuenta" in page
