"""``hubs.custom_domain.record``: what the hourly check writes of a domain, what of it the Hub is owed and what its owner
hears (``test_check_custom_domains.py`` is the check itself)."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from live.errors import PermissionDenied
from live.models import OutboxEvent

from hubs import events
from hubs.models import CustomDomain
from hubs.schemas.custom_domains import CustomDomainRecordIn
from hubs.services.custom_domain_checks import custom_domain_record
from hubs.services.hub_callbacks import system_ctx_for
from hubs.tests.conftest import ctx_for
from hubs.tests.custom_domain_states import ARN, Reason, State, active, attached, hub_of, pending

pytestmark = pytest.mark.django_db


def record(row, **facts):
    data = CustomDomainRecordIn(**{"id": row.id, "expected_state": row.state, **facts})
    return custom_domain_record(system_ctx_for(row.hub_id), data).recorded


def told(hub):
    return OutboxEvent.objects.filter(name=events.CUSTOM_DOMAIN_CHANGED, payload={"business_id": str(hub.id)}).count()


def test_only_the_platform_records(owner, standard_business):
    row = pending(standard_business)

    with pytest.raises(PermissionDenied) as refused:
        custom_domain_record(ctx_for(owner), CustomDomainRecordIn(id=row.id, expected_state=row.state, failures=1))

    assert refused.value.code == "internal_command"


def test_it_takes_the_row_so_the_owner_and_the_check_never_interleave(standard_business):
    row = pending(standard_business)

    with CaptureQueriesContext(connection) as seen:
        record(row, failures=1)

    assert any('FROM "hubs_customdomain"' in query["sql"] and "FOR UPDATE" in query["sql"] for query in seen.captured_queries)


def test_a_domain_that_is_gone_is_not_recorded(standard_business):
    row = pending(standard_business)
    CustomDomain.objects.all().delete()

    assert record(row, failures=1) is False
    assert not CustomDomain.objects.exists()


def test_a_domain_that_left_the_state_is_not_recorded(standard_business):
    row = pending(standard_business)

    assert record(row, expected_state=State.ACTIVE, failures=1) is False
    row.refresh_from_db()
    assert row.failures == 0


def test_only_what_is_given_changes(standard_business):
    row = attached(standard_business, reason=Reason.PROBE_FAILED, failures=2, proven_at=timezone.now())
    unchanged = ("state", "reason", "certificate_token", "certificate_arn", "attached_at", "validation_name", "validation_value", "proven_at", "activated_at", "failures")
    before = [getattr(row, field) for field in unchanged]

    assert record(row) is True

    row.refresh_from_db()
    assert [getattr(row, field) for field in unchanged] == before
    assert row.checked_at is not None


def test_each_thing_given_is_written(standard_business):
    row = pending(standard_business)

    record(row, reason=Reason.DNS_UNAVAILABLE, certificate_arn=ARN, validation_name="_n", validation_value="_v", failures=1)

    row.refresh_from_db()
    assert (row.reason, row.certificate_arn, row.validation_name, row.validation_value, row.failures) == (
        Reason.DNS_UNAVAILABLE,
        ARN,
        "_n",
        "_v",
        1,
    )


def test_a_domain_is_connected_since_it_became_active_and_never_since_it_lapsed(standard_business):
    row = attached(standard_business, proven_at=timezone.now())

    record(row, state=State.ACTIVE)
    row.refresh_from_db()
    connected = row.activated_at
    assert connected is not None

    record(row, state=State.LAPSED)
    row.refresh_from_db()
    assert (row.state, row.activated_at) == (State.LAPSED, connected)


def test_a_new_certificate_has_a_new_token(standard_business):
    row = pending(standard_business)
    token = row.certificate_token

    record(row, new_token=True)

    row.refresh_from_db()
    assert row.certificate_token != token


def test_a_proof_keeps_the_date_it_was_first_had(standard_business):
    first = timezone.now() - timedelta(days=3)
    row = attached(standard_business, proven_at=first)

    record(row, proven=True)

    row.refresh_from_db()
    assert row.proven_at == first


@pytest.mark.parametrize(
    ("make", "owed"),
    [(active, 1), (pending, 0)],
    ids=["the Hub was told of it", "the Hub never heard of it"],
)
def test_a_domain_forgotten_leaves_the_snapshot_it_was_in_and_its_owner_hears(standard_business, make, owed):
    row = make(standard_business)
    version, heard = hub_of(standard_business).state_version, told(standard_business)

    assert record(row, forget=True) is True

    assert not CustomDomain.objects.exists()
    assert hub_of(standard_business).state_version == version + owed
    assert told(standard_business) == heard + 1


@pytest.mark.parametrize(
    ("facts", "owed"),
    [({"failures": 1}, 0), ({"failures": 1, "owe_snapshot": True}, 1), ({"proven": False}, 1)],
    ids=["what the Hub is not told", "the Hub has to be told again", "out of the snapshot"],
)
def test_the_hub_is_owed_a_newer_snapshot_only_when_it_has_something_to_hear(standard_business, facts, owed):
    row = active(standard_business)
    version = hub_of(standard_business).state_version

    record(row, **facts)

    assert hub_of(standard_business).state_version == version + owed


@pytest.mark.parametrize(("facts", "heard"), [({}, 0), ({"reason": Reason.PROBE_FAILED}, 1)], ids=["nothing new", "a new reason"])
def test_the_owner_hears_only_of_what_they_see(standard_business, facts, heard):
    row = active(standard_business)
    before = told(standard_business)

    record(row, **facts)

    assert told(standard_business) == before + heard
