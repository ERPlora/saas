"""HUBS-F16: the owner changes the web address of a business (``hubs.business.change_address``).

PLAN-SAAS §1.1, round 2026-10-15b: «Cambiar el subdominio … SE PORTA: Ajustes del negocio (dueño), validado contra
``packages/live/live/slugs.py``; el Hub lo recibe en la foto». Cases from ERPlora/saas ``apps/dashboard/hubs/main``
(origin/develop) ``change-subdomain`` and its flow SAAS_DASHBOARD-F10, whose trap this closes: the old door rewrote
the address without moving the business, so it kept answering on the old one while erplora.com linked to the new.
Here the address the Hub registers (``PUT /internal/hubs/{id}``) and the photo both carry the new one, and the old
address stays the business's own: nobody else can take it and land the old links and QR codes.
"""

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from accounts.models import HubMembership
from hubs import events, queries, services
from hubs.models import Hub
from hubs.schemas import BusinessAddressIn, ByIdIn
from hubs.tests.conftest import create_business, ctx_for

pytestmark = pytest.mark.django_db


def change(user, hub, slug):
    return services.business_change_address(ctx_for(user), BusinessAddressIn(id=hub.id, slug=slug))


class TestChangeTheAddress:
    def test_the_owner_moves_the_business_to_the_new_address(self, business, owner):
        before = Hub.objects.values("registry_version", "state_version").get(pk=business.pk)
        Hub.objects.filter(pk=business.pk).update(pending_hub_call="")

        detail = change(owner, business, "casa-manolo")
        business.refresh_from_db()

        assert (business.slug, business.previous_slug) == ("casa-manolo", "bar-manolo")
        assert detail.host == queries.host_of("casa-manolo")
        # The Hub registers it (the registry) and the photo carries it: both owed and pushed after the COMMIT.
        assert business.pending_hub_call == "put"
        assert business.registry_version == before["registry_version"] + 1
        assert business.state_version == before["state_version"] + 1
        assert queries.hub_registry(business.id)["slug"] == "casa-manolo"

    def test_it_records_its_event(self, business, owner):
        change(owner, business, "casa-manolo")

        assert OutboxEvent.objects.filter(name=events.BUSINESS_ADDRESS_CHANGED).count() == 1

    def test_the_same_address_changes_nothing(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(pending_hub_call="")

        change(owner, business, "bar-manolo")
        business.refresh_from_db()

        assert (business.pending_hub_call, business.previous_slug) == ("", "")

    def test_the_jump_follows_the_business_to_its_new_address(self, business, owner):
        change(owner, business, "casa-manolo")

        assert not HubMembership.objects.filter(hub_slug="bar-manolo").exists()
        assert HubMembership.objects.filter(hub_slug="casa-manolo", user=owner).exists()
        assert queries.verify_access_mirror() == []

    def test_the_hub_receives_the_new_address(self, business, owner, hub_double, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            change(owner, business, "casa-manolo")

        assert hub_double.registry[str(business.id)]["slug"] == "casa-manolo"


class TestTheOldAddressStaysTheBusinesss:
    def test_another_business_cannot_take_it(self, business, owner, make_user):
        change(owner, business, "casa-manolo")
        other = create_business(make_user("other@example.com"), name="Otro Bar")

        with pytest.raises(Conflict) as refused:
            change(other.members.get().user, other, "bar-manolo")

        assert refused.value.code == "hubs.slug_taken"
        assert queries.free_slug("Bar Manolo") == "bar-manolo-2"

    def test_the_business_can_go_back_to_it(self, business, owner):
        change(owner, business, "casa-manolo")
        change(owner, business, "bar-manolo")
        business.refresh_from_db()

        assert (business.slug, business.previous_slug) == ("bar-manolo", "casa-manolo")


class TestRefusals:
    @pytest.mark.parametrize("slug", ["hubs", "www", "admin"])
    def test_a_reserved_address(self, business, owner, slug):
        with pytest.raises(Conflict) as refused:
            change(owner, business, slug)

        assert refused.value.code == "hubs.slug_reserved"

    @pytest.mark.parametrize("slug", ["Casa Manolo", "-casa", "casa_manolo", "ab", "xn--casa"])
    def test_an_address_the_hub_would_not_accept(self, business, owner, slug):
        with pytest.raises(InvalidPayload) as refused:
            change(owner, business, slug)

        assert "slug" in refused.value.fields

    def test_an_address_another_business_has(self, business, owner, make_user):
        create_business(make_user("other@example.com"), name="Casa Manolo")

        with pytest.raises(Conflict) as refused:
            change(owner, business, "casa-manolo")

        assert refused.value.code == "hubs.slug_taken"

    def test_a_demo_address(self, business, owner):
        with pytest.raises(Conflict) as refused:
            change(owner, business, "demo-1a2b3c4d")

        assert refused.value.code == "hubs.slug_reserved"

    def test_a_deleted_business_keeps_its_address(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(Conflict) as refused:
            change(owner, business, "casa-manolo")

        assert refused.value.code == "hubs.business_deleted"

    @pytest.mark.parametrize("who", ["admin", "manager", "employee"])
    def test_only_the_owner_changes_it(self, business, team, who):
        with pytest.raises(PermissionDenied):
            change(team[who], business, "casa-manolo")

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_somebody_without_access_does_not_learn_it_exists(self, business, team, who):
        with pytest.raises(NotFound):
            change(team[who], business, "casa-manolo")


class TestThePageSaysWhoMay:
    def test_only_the_owner_gets_the_button(self, business, team):
        get = queries.business_get

        assert get(ctx_for(team["owner"]), ByIdIn(id=business.id)).can.change_address is True
        assert get(ctx_for(team["admin"]), ByIdIn(id=business.id)).can.change_address is False

    def test_not_on_a_deleted_business(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        assert queries.business_get(ctx_for(owner), ByIdIn(id=business.id)).can.change_address is False
