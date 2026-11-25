"""``manage.py create_platform_business <hub id> --owner <email> [--execute]``: ERPlora's own business enters erplora.com.

A dry run unless ``--execute``, as the Hub's ``create_platform_hub``; run again, it changes nothing.
"""

import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from hubs.models import Hub, HubMember
from hubs.tests.conftest import platform_hub_in

pytestmark = pytest.mark.django_db

COMMAND = "create_platform_business"


def run(*args) -> str:
    out = StringIO()
    call_command(COMMAND, *args, stdout=out)
    return out.getvalue()


def test_without_execute_nothing_is_written_and_it_says_what_it_would_do(
    hub_double, founder, django_capture_on_commit_callbacks
):
    hub_id = platform_hub_in(hub_double)

    with django_capture_on_commit_callbacks(execute=True):
        out = run(str(hub_id), "--owner", founder.email)

    assert "Dry run" in out
    assert str(hub_id) in out
    assert not Hub.objects.exists()
    assert [call.method for call in hub_double.calls] == ["GET"]


def test_with_execute_the_row_its_owner_and_its_people_are_made(
    hub_double, founder, django_capture_on_commit_callbacks
):
    hub_id = platform_hub_in(hub_double)

    with django_capture_on_commit_callbacks(execute=True):
        out = run(str(hub_id), "--owner", founder.email, "--execute")

    hub = Hub.objects.get(is_platform=True)
    assert (hub.id, hub.slug) == (hub_id, "erp")
    assert HubMember.objects.get(hub=hub).user == founder
    assert hub.pushed_state_version == 1
    assert "Dry run" not in out


def test_again_it_says_it_is_there_and_changes_nothing(hub_double, founder, make_user):
    hub_id = platform_hub_in(hub_double)
    run(str(hub_id), "--owner", founder.email, "--execute")
    other = make_user("other@example.com")

    out = run(str(hub_id), "--owner", other.email, "--execute")

    assert "already" in out
    assert HubMember.objects.get().user == founder


@pytest.mark.parametrize("extra", [(), ("--execute",)])
def test_a_hub_that_is_not_erploras_own_ends_it_with_an_error(hub_double, founder, extra):
    hub_id = platform_hub_in(hub_double, slug="bar-manolo")

    with pytest.raises(CommandError, match="hubs.platform_hub_mismatch"):
        run(str(hub_id), "--owner", founder.email, *extra)

    assert not Hub.objects.exists()


def test_with_the_hub_away_it_ends_with_an_error(offline_hub, founder):
    with pytest.raises(CommandError, match="hubs.platform_hub_unchecked"):
        run(str(uuid.uuid7()), "--owner", founder.email, "--execute")


def test_an_owner_without_an_account_ends_it_with_an_error(hub_double, db):
    with pytest.raises(CommandError, match="hubs.platform_owner_unknown"):
        run(str(platform_hub_in(hub_double)), "--owner", "nobody@example.com", "--execute")


def test_an_id_that_is_no_uuid_is_refused_before_anything(hub_double, founder):
    with pytest.raises(CommandError):
        run("erp", "--owner", founder.email, "--execute")

    assert hub_double.calls == []


def test_the_owner_is_mandatory(hub_double, db):
    with pytest.raises(CommandError):
        run(str(platform_hub_in(hub_double)), "--execute")
