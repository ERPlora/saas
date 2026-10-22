"""FIX-SAAS-WHATSAPP-E2E-SEED-TEMPLATES-AND-USAGE · erplora.com's side of WhatsApp's cross e2e with a real Hub
(``tests/e2e/panel/whatsapp_hub_seed.py``, the one the Hub's ``tests/e2e/whatsapp-helpers.ts`` runs).

Besides ``a``'s number, the seed keeps the templates erplora.com would hold after reading Meta's list (approved, in
review and rejected with Meta's reason, one made in WhatsApp Manager with a photo header) and this month's usage
(``--used N``, 0 by default), so the snapshot the Hub takes (door 4) shows them: the Hub's WHATSAPP_INBOX-F27, F28
and the cap of F13 end to end. Meta is never called (``respx`` with no route refuses any call to it); the Hub is the
real-HTTP double (``hubs.tests.hub_double``).
"""

import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest
import respx
from django.utils import timezone

from hubs import queries as hubs_queries
from hubs.models import Hub
from hubs.tests.conftest import create_business
from whatsapp import queries
from whatsapp.models import Template, Usage
from whatsapp.tests.test_channel_contract import HubChannelSyncIn
from whatsapp.tests.test_internal import door, error_code, internal  # noqa: F401 - shared fixtures

SEED = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "panel" / "whatsapp_hub_seed.py"
SEND_PATH = "/internal/whatsapp/send"
SENT = {"messaging_product": "whatsapp", "messages": [{"id": "wamid.e2e-seed"}]}

pytestmark = pytest.mark.django_db


def _load():
    spec = importlib.util.spec_from_file_location("whatsapp_hub_seed", SEED)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seed_module(monkeypatch):
    """The seed as a module; pytest set Django up already (its ``setup_django`` would configure the logging again)."""
    module = _load()
    monkeypatch.setattr(module, "setup_django", lambda: None)
    return module


@pytest.fixture
def ids():
    return {"a": uuid.uuid7(), "b": uuid.uuid7()}


@pytest.fixture
def run(seed_module, ids, settings, internal, hub_double, capsys):  # noqa: F811 - the fixture of test_internal
    """Runs the seed as the Hub's e2e does (``main``, development only), Meta refusing to be called: its JSON line."""
    settings.DEBUG = True

    def go(*options: str) -> dict:
        with respx.mock:
            seed_module.main([str(ids["a"]), str(ids["b"]), *options])
        return json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    return go


def _templates(hub_id):
    return list(Template.objects.filter(hub_id=hub_id).order_by("name", "language"))


def _month() -> str:
    return timezone.now().strftime("%Y-%m")


def test_a_gets_metas_templates_approved_in_review_and_rejected_with_its_reason(run, ids):
    run()

    rows = _templates(ids["a"])
    assert {row.status for row in rows} >= {"APPROVED", "PENDING", "REJECTED"}
    assert all(row.rejected_reason for row in rows if row.status == "REJECTED")
    assert not any(row.rejected_reason for row in rows if row.status != "REJECTED")
    # F28: one made in WhatsApp Manager the Hub cannot fill (a photo header, a named variable).
    assert any(row.header_format == "IMAGE" for row in rows)
    # The Hub's e2e delete what a run leaves by this prefix (whatsapp-helpers.ts, `cleanUp`).
    assert all(row.name.startswith("e2e_") for row in rows)
    assert all(row.meta_id for row in rows)
    assert _templates(ids["b"]) == []


def test_the_snapshot_the_hub_takes_carries_the_templates_and_the_months_usage(run, ids, hub_double):
    printed = run("--used", "7")

    # The Hub's e2e compares the line whole (`toEqual`): nothing more than these two keys.
    assert printed == {"delivered": True, "hub_error": ""}
    pushed = hub_double.calls_to("PUT", f"/internal/hubs/{ids['a']}/state")[-1].body["whatsapp"]
    HubChannelSyncIn.model_validate(pushed)
    assert pushed["status"] == "connected"
    assert pushed["monthly_usage"] == 7
    assert pushed["usage_month"] == _month()
    plan = hubs_queries.effective_plan(ids["a"], timezone.now())
    assert pushed["monthly_limit"] == plan.whatsapp_messages_per_month
    seeded = {(row.name, row.language, row.status) for row in _templates(ids["a"])}
    assert {(t["name"], t["language"], t["status"]) for t in pushed["templates"]} == seeded
    assert queries.channel_block(ids["a"])["templates"] == pushed["templates"]


def test_used_at_the_plans_allowance_has_erplora_refuse_a_send_without_calling_meta(run, ids, client):
    run()
    limit = hubs_queries.effective_plan(ids["a"], timezone.now()).whatsapp_messages_per_month
    run("--used", str(limit))

    with respx.mock:
        meta = respx.route(host="graph.facebook.com")
        response = door(client, SEND_PATH, {"hub": "a", "to": "+34699000001", "type": "text", "text": "Hola"})

    assert (response.status_code, error_code(response)) == (409, "whatsapp.cap_reached")
    assert not meta.called


def test_by_default_the_usage_is_zero_and_a_send_still_leaves(run, ids, client):
    run("--used", "3")
    run()

    assert Usage.objects.get(hub_id=ids["a"], month=_month()).used == 0
    with respx.mock:
        meta = respx.route(host="graph.facebook.com").mock(return_value=httpx.Response(200, json=SENT))
        response = door(client, SEND_PATH, {"hub": "a", "to": "+34699000001", "type": "text", "text": "Hola"})

    assert response.status_code == 200
    assert meta.called


def test_running_it_again_keeps_one_of_each(run, ids, seed_module):
    run("--used", "5")
    first = [(row.pk, row.name, row.language) for row in _templates(ids["a"])]
    run("--used", "5")

    assert [(row.pk, row.name, row.language) for row in _templates(ids["a"])] == first
    assert len(first) == len(seed_module.TEMPLATES)
    assert Usage.objects.filter(hub_id=ids["a"]).count() == 1


def test_running_it_again_with_another_usage_pushes_it_to_the_hub(run, ids, hub_double):
    run("--used", "5")
    run("--used", "9")

    pushed = hub_double.calls_to("PUT", f"/internal/hubs/{ids['a']}/state")[-1].body["whatsapp"]
    assert pushed["monthly_usage"] == 9


def test_running_it_again_keeps_a_template_the_run_added(run, ids):
    # Not ``complete``: what a run registered at Meta (a template the seed does not list) is not deleted.
    run()
    Template.objects.create(hub_id=ids["a"], name="e2e_run_added", language="es", status="APPROVED")
    run()

    assert Template.objects.filter(hub_id=ids["a"], name="e2e_run_added", language="es").exists()


def test_a_and_b_take_the_hubs_ids_even_after_another_business_was_made(run, ids, make_user):
    create_business(make_user("before@example.com"))

    run()

    assert set(Hub.objects.filter(slug__in=["a", "b"]).values_list("slug", "id")) == {("a", ids["a"]), ("b", ids["b"])}


def test_after_it_a_new_business_takes_a_new_id(run, ids, make_user):
    run()

    assert create_business(make_user("after@example.com")).id not in ids.values()


@pytest.mark.parametrize("value", ["-1", "x", "1.5", ""])
def test_the_usage_is_a_whole_number_not_below_zero(run, ids, value):
    with pytest.raises(SystemExit):
        run("--used", value)

    assert not Hub.objects.filter(pk=ids["a"]).exists()


def test_it_refuses_to_run_without_debug(seed_module, ids, settings):
    settings.DEBUG = False

    with pytest.raises(SystemExit):
        seed_module.main([str(ids["a"]), str(ids["b"])])

    assert not Template.objects.exists()
    assert not Hub.objects.filter(pk=ids["a"]).exists()
