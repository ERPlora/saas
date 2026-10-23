"""ASSISTANT-F23 (ASSISTANT-G58) · Receive the report of an answer of the assistant: the person marks an answer as
wrong, harmful, not what was asked or other, and the Hub sends it (``POST /internal/assistant/report``) with the
question and the answer. erplora.com mails it to the support mailbox, as «Report a problem» (ACCOUNTS-F38), and keeps
nothing: the old product kept the report (question, answer and comment) for ever, fused reports of different
businesses whose answers began alike and opened an issue on GitHub (SAAS_ASSISTANT-F21, «parcial»). The same answer
reported twice in a day mails once. Each business has its own budget of reports.
"""

import io
import logging

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import Client

from assistant.tests.doors import door, error_code

REPORT = "/internal/assistant/report"
ANSWER = "Rosalía Quintanar le debe 400 euros, cóbrele hoy."

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


def report(business, **change) -> dict:
    return {
        "hub": business.slug,
        "message_id": "msg_01",
        "reason": "incorrect",
        "comment": "No es verdad",
        "question": "¿Quién me debe dinero?",
        "answer": ANSWER,
        **change,
    }


def test_the_report_reaches_the_support_mailbox_with_the_business(client, internal, business, settings):
    settings.SUPPORT_EMAIL = "support@erplora.test"

    response = door(client, REPORT, report(business))

    assert response.status_code == 202
    assert response.json() == {"sent": True, "duplicate": False}
    [sent] = mail.outbox
    assert sent.to == ["support@erplora.test"]
    assert sent.subject == f"[Assistant report] {business.name} · incorrect"
    assert business.slug in sent.body and str(business.id) in sent.body
    assert "No es verdad" in sent.body and "¿Quién me debe dinero?" in sent.body and ANSWER in sent.body


def test_the_same_answer_reported_twice_mails_once(client, internal, business):
    door(client, REPORT, report(business))

    again = door(client, REPORT, report(business, comment="Otra vez"))

    assert (again.status_code, again.json()) == (202, {"sent": False, "duplicate": True})
    assert len(mail.outbox) == 1


def test_the_same_message_id_of_another_business_is_its_own_report(client, internal, business, make_user):
    from hubs.models import Hub
    from hubs.tests.conftest import create_business

    other = create_business(make_user("pepe@example.com"), name="Bar Pepe")
    Hub.objects.filter(pk=other.pk).update(status=Hub.Status.ACTIVE)
    door(client, REPORT, report(business))

    assert door(client, REPORT, report(other)).json()["sent"] is True
    assert len(mail.outbox) == 2


def test_a_demo_reports_too(client, internal):
    response = door(client, REPORT, {"message_id": "m", "reason": "harmful", "answer": "x", "hub": "demo-1a2b3c4d"})

    assert response.status_code == 202
    assert "demo-1a2b3c4d" in mail.outbox[0].subject


def test_long_texts_are_cut(client, internal, business):
    door(client, REPORT, report(business, answer="a" * 10_000))

    assert "a" * 4000 in mail.outbox[0].body
    assert "a" * 4001 not in mail.outbox[0].body


@pytest.mark.parametrize("change", [{"reason": "boring"}, {"message_id": ""}, {"answer": ""}])
def test_a_report_without_its_answer_its_id_or_a_known_reason_is_refused(client, internal, business, change):
    response = door(client, REPORT, report(business, **change))

    assert (response.status_code, error_code(response)) == (422, "invalid_payload")
    assert mail.outbox == []


def test_a_mail_that_cannot_leave_says_so_and_can_be_sent_again(client, internal, business, monkeypatch):
    def fail(self, *args, **kwargs):
        raise OSError("the mail server is down")

    with monkeypatch.context() as broken:
        broken.setattr("django.core.mail.message.EmailMessage.send", fail)
        failed = door(client, REPORT, report(business))

    assert (failed.status_code, error_code(failed)) == (503, "assistant.report_not_sent")
    assert door(client, REPORT, report(business)).json() == {"sent": True, "duplicate": False}


def gone_after_the_signature(monkeypatch, business, change):
    """The door resolves the business, and ``change`` happens to it before the report is sent."""
    from assistant import internal as doors

    resolve = doors.resolve

    def resolve_then_change(hub):
        caller = resolve(hub)
        change(business)
        return caller

    monkeypatch.setattr(doors, "resolve", resolve_then_change)


def purge(business):
    business.__class__.objects.filter(pk=business.pk).delete()


def mark(status):
    return lambda business: business.__class__.objects.filter(pk=business.pk).update(status=status)


@pytest.mark.parametrize(
    ("change", "answer"),
    [
        (purge, (404, "hub_unknown")),
        (mark("deleted"), (404, "hub_unknown")),
        (mark("suspended"), (403, "hub_inactive")),
    ],
    ids=["its row purged", "purged", "suspended"],
)
def test_a_business_that_stops_working_after_the_signature_gets_the_doors_answer_and_mails_nothing(
    client, internal, business, monkeypatch, change, answer
):
    gone_after_the_signature(monkeypatch, business, change)

    response = door(client, REPORT, report(business))

    assert (response.status_code, error_code(response)) == answer
    assert mail.outbox == []


def test_a_report_refused_because_the_business_stopped_working_can_be_sent_once_it_works_again(
    client, internal, business, monkeypatch
):
    with monkeypatch.context() as stopped:
        gone_after_the_signature(stopped, business, mark("suspended"))
        assert door(client, REPORT, report(business)).status_code == 403
    mark("active")(business)

    assert door(client, REPORT, report(business)).json() == {"sent": True, "duplicate": False}


def test_a_report_whose_event_cannot_be_written_mails_nothing_and_can_be_sent_again(
    client, internal, business, monkeypatch
):
    def outbox_down(*args, **kwargs):
        raise RuntimeError("the outbox is down")

    with monkeypatch.context() as broken:
        broken.setattr("assistant.services.record_event", outbox_down)
        with pytest.raises(RuntimeError):
            door(client, REPORT, report(business))

    assert mail.outbox == []
    assert door(client, REPORT, report(business)).json() == {"sent": True, "duplicate": False}


def test_a_report_sent_is_one_event_and_a_mail_that_cannot_leave_leaves_none(client, internal, business, monkeypatch):
    from live.models import OutboxEvent

    def fail(self, *args, **kwargs):
        raise OSError("the mail server is down")

    with monkeypatch.context() as broken:
        broken.setattr("django.core.mail.message.EmailMessage.send", fail)
        assert door(client, REPORT, report(business)).status_code == 503
    assert not OutboxEvent.objects.filter(name="assistant.report.sent").exists()

    door(client, REPORT, report(business))

    assert OutboxEvent.objects.filter(name="assistant.report.sent").count() == 1


def test_nothing_of_the_report_is_kept_nor_logged(client, internal, business, caplog):
    caplog.set_level(logging.DEBUG)

    door(client, REPORT, report(business))

    kept = io.StringIO()
    call_command("dumpdata", stdout=kept)
    assert "Rosalía" not in kept.getvalue()
    assert "Rosalía" not in "\n".join(record.getMessage() for record in caplog.records)


def test_the_reports_have_their_own_budget(client, internal, business, settings):
    settings.ASSISTANT_REPORT_RATELIMIT = "1/h"
    door(client, REPORT, report(business))

    assert error_code(door(client, REPORT, report(business, message_id="msg_02"))) == "rate_limited"

