"""Changing a business's settings, ``hubs.business.update``: the owner and an admin change them, only what is
sent changes and a change reaches the Hub after the COMMIT; the country locks once the business is ready.
"""

import pytest
from django.utils import timezone
from live.models import OutboxEvent
from live.errors import Conflict, NotFound, PermissionDenied

from hubs import events, queries, services
from hubs.models import Hub
from hubs.schemas.businesses import BusinessUpdateIn
from hubs.schemas.common import ByIdIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


# --- Updating -------------------------------------------------------------------------------------


class TestUpdate:
    def test_the_owner_and_an_admin_change_the_settings(self, business, team):
        for who, name in (("owner", "Bar Manolo SL"), ("admin", "Bar Manolo")):
            services.business_settings.business_update(
                ctx_for(team[who]), BusinessUpdateIn(id=business.id, name=name)
            )
            business.refresh_from_db()
            assert business.name == name

    def test_only_what_is_sent_changes(self, business, owner):
        services.business_settings.business_update(
            ctx_for(owner),
            BusinessUpdateIn(id=business.id, language="en", timezone="Atlantic/Canary"),
        )
        business.refresh_from_db()

        assert (
            business.name,
            business.language,
            business.timezone,
            business.country,
        ) == (
            "Bar Manolo",
            "en",
            "Atlantic/Canary",
            "ES",
        )

    def test_a_change_owes_the_hub_its_registry(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(pending_hub_call="")

        services.business_settings.business_update(
            ctx_for(owner), BusinessUpdateIn(id=business.id, name="New name")
        )
        business.refresh_from_db()

        assert business.pending_hub_call == "put"

    def test_no_change_owes_nothing(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(pending_hub_call="")

        services.business_settings.business_update(
            ctx_for(owner), BusinessUpdateIn(id=business.id, name="Bar Manolo")
        )
        business.refresh_from_db()

        assert business.pending_hub_call == ""

    def test_a_change_records_its_event_and_no_change_records_none(self, business, owner):
        """HUBS-F15 «Sale»: ``hubs.business.updated``, only when something changed."""
        services.business_settings.business_update(ctx_for(owner), BusinessUpdateIn(id=business.id, name="Bar Manolo"))
        assert not OutboxEvent.objects.filter(name=events.BUSINESS_UPDATED).exists()

        services.business_settings.business_update(ctx_for(owner), BusinessUpdateIn(id=business.id, name="New name"))

        (event,) = OutboxEvent.objects.filter(name=events.BUSINESS_UPDATED)
        assert event.payload == {"id": str(business.id)}

    def test_a_new_name_reaches_the_hub(self, business, owner, hub_double, django_capture_on_commit_callbacks):
        """HUBS-F15: in the old SaaS the new name never reached the hub (its screen, its
        receipts). Here the registry the Hub keeps is pushed again with it after the COMMIT."""
        with django_capture_on_commit_callbacks(execute=True):
            services.business_settings.business_update(ctx_for(owner), BusinessUpdateIn(id=business.id, name="Casa Manolo"))

        assert hub_double.registry[str(business.id)]["name"] == "Casa Manolo"

    @pytest.mark.parametrize("name", ["", "   "])
    def test_an_empty_name_is_not_saved(self, client, business, owner, name):
        """HUBS-F15: the old page saved an empty name."""
        import json

        client.force_login(owner)

        response = client.post(
            "/api/hubs/businesses/update",
            json.dumps({"id": str(business.id), "name": name}),
            content_type="application/json",
            HTTP_HOST="localhost:8001",
        )
        business.refresh_from_db()

        assert response.status_code == 422
        assert "name" in response.json()["error"]["fields"]
        assert business.name == "Bar Manolo"

    @pytest.mark.parametrize("who", ["manager", "employee"])
    def test_a_manager_or_an_employee_only_opens(self, business, team, who):
        with pytest.raises(PermissionDenied):
            services.business_settings.business_update(
                ctx_for(team[who]), BusinessUpdateIn(id=business.id, name="Mine")
            )

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_somebody_without_access_does_not_even_learn_it_exists(
        self, business, team, who
    ):
        with pytest.raises(NotFound):
            services.business_settings.business_update(
                ctx_for(team[who]), BusinessUpdateIn(id=business.id, name="Mine")
            )

    def test_a_deleted_business_is_not_changed(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(Conflict) as refused:
            services.business_settings.business_update(
                ctx_for(owner), BusinessUpdateIn(id=business.id, name="Mine")
            )

        assert refused.value.code == "hubs.business_deleted"


class TestTheCountryLocksOnceReady:
    """The country is not changed once the business is ready (its fiscal series
    and records belong to one country). The SaaS does not see the invoices, which live in the Hub: the lock
    starts when the Hub reports the business ready (``ready_at``), the earliest moment it can invoice."""

    def ready(self, business):
        Hub.objects.filter(pk=business.pk).update(
            ready_at=timezone.now(), status=Hub.Status.ACTIVE
        )

    def test_while_it_is_prepared_the_country_still_changes(self, business, owner):
        services.business_settings.business_update(
            ctx_for(owner), BusinessUpdateIn(id=business.id, country="PT")
        )

        assert Hub.objects.get(pk=business.pk).country == "PT"

    def test_once_ready_a_new_country_is_refused_and_nothing_changes(
        self, business, owner
    ):
        self.ready(business)

        with pytest.raises(Conflict) as refused:
            services.business_settings.business_update(
                ctx_for(owner),
                BusinessUpdateIn(id=business.id, name="Renamed", country="PT"),
            )

        assert refused.value.code == "hubs.country_locked"
        assert (
            Hub.objects.get(pk=business.pk).country,
            Hub.objects.get(pk=business.pk).name,
        ) == ("ES", "Bar Manolo")

    def test_once_ready_the_same_country_sent_again_is_no_change(self, business, owner):
        self.ready(business)

        detail = services.business_settings.business_update(
            ctx_for(owner),
            BusinessUpdateIn(id=business.id, name="Renamed", country="es"),
        )

        assert (detail.name, detail.country) == ("Renamed", "ES")

    def test_the_page_says_whether_the_country_is_locked(self, business, owner):
        before = queries.businesses.business_get(
            ctx_for(owner), ByIdIn(id=business.id)
        ).country_locked
        self.ready(business)

        assert (
            before,
            queries.businesses.business_get(ctx_for(owner), ByIdIn(id=business.id)).country_locked,
        ) == (False, True)

    def test_over_http_it_is_a_409_with_its_code(self, client, business, owner):
        import json

        self.ready(business)
        client.force_login(owner)

        response = client.post(
            "/api/hubs/businesses/update",
            json.dumps({"id": str(business.id), "country": "FR"}),
            content_type="application/json",
            HTTP_HOST="localhost:8001",
        )

        assert (response.status_code, response.json()["error"]["code"]) == (
            409,
            "hubs.country_locked",
        )
