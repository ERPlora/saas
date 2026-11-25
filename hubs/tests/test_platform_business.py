"""ERPlora's own business enters erplora.com once, with the id it already has in the Hub and nothing to pay.

``hubs.platform_business.create`` asks the Hub about that id first: only its own hub, ready under its reserved name and
no demo, is taken. The row is born active and owing the Hub its people and nothing else.
"""

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from live.context import Scope, system_context
from live.errors import OperationError, PermissionDenied

from accounts.tests.conftest import enter
from hubs.models import BillingProfile, Hub, HubMember, Subscription
from hubs.schemas.platform_business import PlatformBusinessIn
from hubs.services import hub_push
from hubs.services.platform_business import platform_business_create
from hubs.tests.conftest import create_business, create_platform_business, ctx_for, platform_hub_in, role_on

pytestmark = pytest.mark.django_db


def create(hub_id, email, ctx=None):
    ctx = ctx or system_context(Scope("user", "system"))
    return platform_business_create(ctx, PlatformBusinessIn(id=hub_id, owner_email=email))


def refused(hub_id, email) -> str:
    with pytest.raises(OperationError) as caught, transaction.atomic():
        create(hub_id, email)
    assert not Hub.objects.filter(is_platform=True).exists()
    return caught.value.code


class TestHowItIsBorn:
    def test_it_bears_the_id_of_the_hub_and_its_reserved_name(self, hub_double, founder):
        hub_id = platform_hub_in(hub_double)

        made = create(hub_id, founder.email)

        hub = Hub.objects.get(is_platform=True)
        assert (made.id, made.slug, made.created) == (hub_id, "erp", True)
        assert (hub.id, hub.slug, hub.name) == (hub_id, "erp", "ERPlora")

    def test_it_is_born_active_and_owing_the_hub_its_people_alone(self, platform_business):
        assert platform_business.status == Hub.Status.ACTIVE
        assert platform_business.ready_at is not None
        assert platform_business.pending_hub_call == ""
        assert (platform_business.state_version, platform_business.pushed_state_version) == (1, 0)

    def test_it_has_no_plan_no_subscription_and_no_payer(self, platform_business):
        assert not Subscription.objects.filter(hub=platform_business).exists()
        assert not BillingProfile.objects.exists()
        assert platform_business.billing_profile is None
        assert platform_business.can_buy_internal_plans is False

    def test_its_owner_is_in_it_without_an_invitation(self, platform_business, founder):
        (member,) = HubMember.objects.filter(hub=platform_business)
        assert (member.user, member.role) == (founder, HubMember.Role.OWNER)
        assert member.accepted_at is not None
        assert role_on(founder, "erp") == "hub_owner"

    def test_its_people_go_out_after_the_commit(self, hub_double, founder, django_capture_on_commit_callbacks):
        hub_id = platform_hub_in(hub_double)

        with django_capture_on_commit_callbacks(execute=True):
            create(hub_id, founder.email)

        (call,) = [call for call in hub_double.calls if call.method != "GET"]
        assert (call.method, call.path) == ("PUT", f"/internal/hubs/{hub_id}/state")
        assert call.body["version"] == 1

    def test_the_owner_is_told_in_its_channel(self, platform_business, founder):
        from live.models import OutboxEvent

        event = OutboxEvent.objects.get(name="hubs.business.created")
        assert (event.scope_kind, event.scope_key) == ("user", str(founder.pk))

    def test_again_with_the_same_id_changes_nothing(self, hub_double, platform_business, make_user):
        make_user("other@example.com")

        made = create(platform_business.id, "other@example.com")

        assert (made.id, made.created) == (platform_business.id, False)
        assert HubMember.objects.filter(hub=platform_business).count() == 1


class TestTheHubIsAskedFirst:
    @pytest.mark.parametrize(
        "answer",
        [
            {"slug": "erplora"},
            {"slug": "bar-manolo"},
            {"slug": None},
            {"status": "migrating"},
            {"status": "failed"},
            {"status": "cancelled"},
            {"is_demo": True},
            {"is_demo": None},
        ],
    )
    def test_any_other_hub_is_refused(self, hub_double, founder, answer):
        hub_id = platform_hub_in(hub_double, **answer)

        assert refused(hub_id, founder.email) == "hubs.platform_hub_mismatch"

    def test_an_answer_that_names_another_id_is_refused(self, hub_double, founder):
        hub_id = uuid.uuid7()
        body = {"id": str(uuid.uuid7()), "slug": "erp", "status": "ready", "is_demo": False}
        hub_double.answer("GET", str(hub_id), 200, body)

        assert refused(hub_id, founder.email) == "hubs.platform_hub_mismatch"

    def test_an_answer_off_the_contract_is_refused(self, hub_double, founder):
        hub_id = uuid.uuid7()
        hub_double.answer("GET", str(hub_id), 200, ["erp"])

        assert refused(hub_id, founder.email) == "hubs.platform_hub_mismatch"

    def test_an_answer_that_is_not_a_plain_200_is_refused(self, hub_double, founder):
        hub_id = uuid.uuid7()
        body = {"id": str(hub_id), "slug": "erp", "status": "ready", "is_demo": False}
        hub_double.answer("GET", str(hub_id), 202, body)

        assert refused(hub_id, founder.email) == "hubs.platform_hub_mismatch"

    def test_an_id_the_hub_does_not_know_is_refused(self, hub_double, founder):
        assert refused(uuid.uuid7(), founder.email) == "hubs.platform_hub_unchecked"

    def test_with_the_hub_away_nothing_is_made(self, offline_hub, founder):
        assert refused(uuid.uuid7(), founder.email) == "hubs.platform_hub_unchecked"


class TestItsOwner:
    def test_an_email_without_an_account_is_refused(self, hub_double):
        assert refused(platform_hub_in(hub_double), "nobody@example.com") == "hubs.platform_owner_unknown"

    def test_an_inactive_account_is_refused(self, hub_double, founder):
        founder.is_active = False
        founder.save(update_fields=["is_active"])

        assert refused(platform_hub_in(hub_double), founder.email) == "hubs.platform_owner_unknown"

    def test_an_account_that_never_proved_its_address_is_refused(self, hub_double, founder):
        from allauth.account.models import EmailAddress

        EmailAddress.objects.create(user=founder, email=founder.email, primary=True, verified=False)

        assert refused(platform_hub_in(hub_double), founder.email) == "hubs.platform_owner_unknown"

    @pytest.mark.parametrize("mark", ["is_staff", "is_superuser"])
    def test_an_account_of_the_staff_is_refused_as_in_any_business(self, hub_double, founder, mark):
        setattr(founder, mark, True)
        founder.save(update_fields=[mark])

        assert refused(platform_hub_in(hub_double), founder.email) == "hubs.platform_account"

    def test_the_email_is_found_whatever_its_case(self, hub_double, founder):
        assert create(platform_hub_in(hub_double), founder.email.upper()).created is True


class TestThereIsOnlyOne:
    def test_another_id_is_refused_once_it_is_here(self, hub_double, platform_business, founder):
        with pytest.raises(OperationError) as caught, transaction.atomic():
            create(platform_hub_in(hub_double), founder.email)

        assert caught.value.code == "hubs.platform_business_taken"
        assert Hub.objects.get(is_platform=True).id == platform_business.id

    def test_the_id_of_a_business_is_never_taken_over(self, hub_double, business, founder):
        hub_double.registry[str(business.id)] = {"slug": "erp", "status": "ready", "is_demo": False}

        assert refused(business.id, founder.email) == "hubs.platform_business_taken"

    def test_a_business_that_already_bears_its_name_stops_it(self, hub_double, founder, make_user):
        enter(make_user("old@example.com"), "erp")

        assert refused(platform_hub_in(hub_double), founder.email) == "hubs.platform_business_taken"

    def test_the_database_keeps_a_second_one_out(self, platform_business):
        with pytest.raises(IntegrityError), transaction.atomic():
            Hub.objects.bulk_create([Hub(slug="erp-2", name="Second", country="ES", is_platform=True, status="active")])


class TestOnlyThePlatformMakesIt:
    def test_an_account_is_refused(self, hub_double, founder):
        with pytest.raises(PermissionDenied) as caught:
            create(platform_hub_in(hub_double), founder.email, ctx=ctx_for(founder))

        assert caught.value.code == "internal_command"
        assert not Hub.objects.filter(is_platform=True).exists()

    def test_it_is_no_tool_of_the_assistant(self):
        from live.operations import INTERNAL, get

        assert get("hubs.platform_business.create").ai is INTERNAL


class TestItsName:
    def test_no_other_business_bears_it(self, owner, plans):
        for reserved in ("erp", "erplora", "test", "hubs"):
            with pytest.raises(OperationError) as caught, transaction.atomic():
                create_business(owner, slug=reserved)
            assert caught.value.code == "hubs.slug_reserved"

    def test_a_business_called_like_it_gets_another_address(self, owner, plans):
        assert create_business(owner, name="ERP").slug == "erp-store"

    def test_saving_a_business_with_it_is_refused_unless_it_is_erploras_own(self, db):
        with pytest.raises(ValidationError):
            Hub(slug="erp", name="Impostor", country="ES").save()

    @pytest.mark.parametrize("reserved", ["erplora", "test", "hubs", "www"])
    def test_erploras_own_bears_no_other_reserved_name(self, db, reserved):
        with pytest.raises(ValidationError):
            Hub(slug=reserved, name="ERPlora", country="ES", is_platform=True).save()


class TestWhatItsRowNeverSays:
    """The database refuses what no door of erplora.com does: whatever path writes it, it fails closed."""

    @pytest.mark.parametrize(
        "change",
        [
            {"status": Hub.Status.SUSPENDED},
            {"status": Hub.Status.PAST_DUE},
            {"status": Hub.Status.DELETING},
            {"status": Hub.Status.DELETED},
            {"pending_hub_call": "put"},
            {"pending_hub_call": "delete"},
            {"pending_hub_call": "restore"},
        ],
    )
    def test_a_state_of_the_plan_or_a_call_owed_to_the_hub(self, platform_business, change):
        with pytest.raises(IntegrityError), transaction.atomic():
            Hub.objects.filter(pk=platform_business.pk).update(**change)

    def test_a_payer(self, platform_business, founder):
        payer = BillingProfile.objects.create(owner=founder)

        with pytest.raises(IntegrityError), transaction.atomic():
            Hub.objects.filter(pk=platform_business.pk).update(billing_profile=payer)

    def test_any_other_business_still_takes_them(self, business, owner):
        payer = BillingProfile.objects.create(owner=owner)
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.SUSPENDED, pending_hub_call="delete", billing_profile=payer
        )

        business.refresh_from_db()
        assert (business.status, business.pending_hub_call) == ("suspended", "delete")


def test_the_platform_business_made_here_is_delivered(hub_double, founder):
    """The helper the other tests build on leaves what one push settles."""
    hub = create_platform_business(platform_hub_in(hub_double), founder)

    assert hub_push.sync_hub(hub.id) is True
    hub.refresh_from_db()
    assert (hub.pushed_state_version, hub.last_hub_error) == (1, "")
