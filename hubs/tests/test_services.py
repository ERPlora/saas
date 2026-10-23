"""The life of a business: ``hubs.business.{create,update,delete,restore,open,mark_ready}`` and the push
to the Hub after each COMMIT (plan 2026-10-13, lot L1-A; round 17 §2).

Cases ported from ERPlora/saas ``apps/dashboard/hubs/main/tests/`` (origin/develop), from views and
DRF to operations: ``test_start`` (the sign-up from one question: a duplicate, reserved or emoji name
never blocks it; a second free hub is refused; a missing Free plan is an error, not a loop),
``test_start_business_type`` (optional, an unknown code is «not said», a retired code resolves to its
survivor), ``test_start_country`` (stored uppercase, a country we do not serve is refused),
``test_api_free_hub_creation`` and ``test_alta_without_org`` (a local Free subscription without Stripe,
the creator is the owner member, the quota is per account and a refusal leaves nothing behind),
``test_free_hub_lifecycle`` (the push waits for the COMMIT), ``test_slug_dedupe``,
``test_owner_provisioning`` (the owner is born with the business), ``test_hub_delete_semantics`` and
``test_deletion_email`` (deleting keeps the record, recoverable for 90 days, and the owner is told the
date), ``test_last_business`` (opening remembers the business) and ``test_hub_handoff`` (opening mints
the one-time code). Dropped with their reason: servers, containers, deploy tasks, progress streams and
htmx pages (there is no container per hub; the panel is a SPA).
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone, translation
from live.models import OutboxEvent
from live.slugs import validate_hub_slug
from live.errors import (
    Conflict,
    InvalidPayload,
    NotFound,
    OperationError,
    PermissionDenied,
    Unauthorized,
)

from accounts.models import AuthExchangeCode, HubMembership
from hubs import events, queries, services
from hubs.models import BillingProfile, BusinessType, Hub, HubMember, Plan, Subscription
from hubs.schemas import (
    BusinessCreateIn,
    BusinessDeleteIn,
    BusinessOpenIn,
    BusinessUpdateIn,
    ByIdIn,
    MarkReadyIn,
)
from hubs.tests.conftest import add_member, create_business, ctx_for

pytestmark = pytest.mark.django_db


def create(user, **data):
    return services.business_create(
        ctx_for(user),
        BusinessCreateIn(**{"name": "Bar Manolo", "country": "ES", **data}),
    )


# --- Creating a business --------------------------------------------------------------------------


class TestTheSignUpFromOneQuestion:
    def test_the_name_alone_creates_the_business(self, owner, plans):
        created = create(owner)

        hub = Hub.objects.get(pk=created.id)
        assert (hub.name, hub.slug, hub.country, hub.status) == (
            "Bar Manolo",
            "bar-manolo",
            "ES",
            "preparing",
        )
        assert hub.id.version == 7
        assert (created.status, created.role) == ("preparing", "hub_owner")

    def test_the_sign_up_records_its_event_for_the_creators_list(self, owner, plans):
        """HUBS-F01 «Sale»: ``hubs.business.created``, in the transaction, on the channel of who created it."""
        hub = create_business(owner)

        (event,) = OutboxEvent.objects.filter(name=events.BUSINESS_CREATED)
        assert (event.payload, event.scope_key) == ({"id": str(hub.id)}, str(owner.id))

    def test_the_creator_is_the_owner_born_answered(self, owner, plans):
        hub = create_business(owner)

        member = HubMember.objects.get(hub=hub)
        assert (member.user, member.role) == (owner, "hub_owner")
        assert member.accepted_at is not None and member.invited_at is None

    def test_a_local_free_subscription_without_stripe(self, owner, plans):
        hub = create_business(owner)

        subscription = Subscription.objects.get(hub=hub)
        assert subscription.plan.slug == "free"
        assert (
            subscription.stripe_subscription_id,
            subscription.stripe_customer_id,
        ) == ("", "")

    def test_free_is_born_without_a_trial(self, owner, plans):
        """Ioan, 2026-10-15: no plan of the catalogue carries a trial; the Free plan is the way in."""
        subscription = Subscription.objects.get(hub=create_business(owner))

        assert (subscription.plan.slug, subscription.trial_plan, subscription.trial_end) == ("free", None, None)
        assert subscription.status != "trialing"

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
    def test_free_is_born_with_the_starter_trial(self, owner, plans):
        """ADR-0474, dormant since 2026-10-15: when staff give Starter a trial, Free is born with its days."""
        before = timezone.now()
        subscription = Subscription.objects.get(hub=create_business(owner))

        assert (subscription.status, subscription.trial_plan.slug) == (
            "trialing",
            "starter",
        )
        assert subscription.trial_end - subscription.trial_start == timedelta(days=15)
        assert subscription.trial_start >= before

    def test_without_a_starter_on_sale_free_is_born_without_trial(self, owner, plans):
        Plan.objects.filter(slug="starter").update(is_active=False)

        subscription = Subscription.objects.get(hub=create_business(owner))

        assert (
            subscription.status,
            subscription.trial_plan,
            subscription.trial_end,
        ) == ("active", None, None)

    def test_a_payer_skeleton_for_the_account(self, owner, plans):
        hub = create_business(owner)

        profile = hub.billing_profile
        assert (profile.owner, profile.billing_email, profile.billing_country) == (
            owner,
            owner.email,
            "ES",
        )
        assert (profile.billing_name, profile.tax_id) == ("", "")

    def test_the_hub_owes_its_registration(self, owner, plans):
        hub = create_business(owner)

        assert (hub.pending_hub_call, hub.state_version, hub.pushed_state_version) == (
            "put",
            1,
            0,
        )
        assert hub.provision_requested_at is not None and hub.ready_at is None

    def test_the_language_is_the_accounts(self, owner, plans):
        assert create_business(owner).language == "es"

    def test_the_owner_may_enter_once_it_is_ready(self, owner, plans):
        """The jump checks the account's access (``accounts.HubMembership``) until it moves to hubs."""
        hub = create_business(owner)

        assert HubMembership.objects.filter(
            user=owner, hub_slug=hub.slug, role="hub_owner"
        ).exists()


class TestTheAddress:
    def test_a_duplicate_name_never_blocks_the_sign_up(self, owner, plans, make_user):
        create(owner)
        other = make_user("other@example.com")

        assert create(other).slug == "bar-manolo-2"
        assert create(make_user("third@example.com")).slug == "bar-manolo-3"

    def test_a_reserved_name_never_blocks_the_sign_up(self, owner, plans):
        assert create(owner, name="Admin").slug == "admin-store"

    def test_a_name_that_slugifies_to_nothing_still_works(self, owner, plans):
        assert create(owner, name="🍕🍕").slug == "my-business"

    def test_a_short_name_gets_room_to_be_an_address(self, owner, plans):
        assert create(owner, name="Yo").slug == "yo-store"

    def test_an_address_of_an_older_account_hub_is_taken_too(self, owner, plans):
        """Hubs of the phase-1 seed exist only as ``accounts.HubMembership`` rows."""
        HubMembership.objects.create(
            user=owner, hub_slug="bar-manolo", role="hub_owner"
        )

        assert create(owner).slug == "bar-manolo-2"

    def test_a_chosen_address_is_kept(self, owner, plans):
        assert create(owner, slug="manolo-bar").slug == "manolo-bar"

    @pytest.mark.parametrize("slug", ["hub", "hubs", "www", "admin"])
    def test_a_chosen_reserved_address_is_a_conflict(self, owner, plans, slug):
        with pytest.raises(Conflict) as refused:
            create(owner, slug=slug)

        assert refused.value.code == "hubs.slug_reserved"
        assert not Hub.objects.exists()

    def test_a_chosen_address_already_taken_is_a_conflict(
        self, owner, plans, make_user
    ):
        create(owner)

        with pytest.raises(Conflict) as refused:
            create(make_user("other@example.com"), slug="bar-manolo")

        assert refused.value.code == "hubs.slug_taken"

    def test_a_malformed_address_is_an_invalid_field(self, owner, plans):
        with pytest.raises(InvalidPayload) as refused:
            create(owner, slug="Bar Manolo")

        assert set(refused.value.fields) == {"slug"}

    # Review of L1-A, finding 1: slugify() keeps "_", which no DNS label (live.slugs) admits; such an
    # address was stored, the Hub refused its registry forever and nobody could enter or rename it.

    def test_an_underscore_never_reaches_the_address(self, owner, plans):
        assert create(owner, name="Bar_Manolo").slug == "bar-manolo"

    def test_a_name_cut_at_an_underscore_never_ends_in_a_hyphen(self, owner, plans):
        name = "a" * 29 + "_bar"  # cut at 30 characters, the last one is the underscore

        slug = create(owner, name=name).slug

        assert slug == "a" * 29
        assert validate_hub_slug(slug) == slug

    # Round 2026-10-17: ``demo-…`` names the demo hubs (live.slugs, ``allow_demo`` only in the Hub's registry). A
    # name like «Demo Bar» proposed ``demo-bar``, which no customer may take: the address fell back to
    # ``my-business`` and lost the name. Now the prefix loses its hyphen.

    def test_a_name_that_starts_like_a_demo_keeps_its_words(self, owner, plans):
        assert create(owner, name="Demo Bar").slug == "demobar"

    def test_the_word_demo_alone_gets_room_to_be_an_address(self, owner, plans):
        assert create(owner, name="Demo").slug == "demostore"

    def test_a_second_demo_bar_is_numbered_as_any_other(self, owner, plans, make_user):
        create(owner, name="Demo Bar")

        assert create(make_user("other@example.com"), name="Demo Bar").slug == "demobar-2"

    @pytest.mark.parametrize("name", ["Demo Bar", "demo-store", "DEMO--Tienda", "Demo_Bar"])
    def test_no_proposed_address_is_a_demo_hubs(self, owner, plans, name):
        slug = queries.free_slug(name)

        assert not slug.startswith("demo-")
        assert validate_hub_slug(slug) == slug

    @pytest.mark.parametrize("slug", ["demo-bar", "demo-0123abcd"])
    def test_a_chosen_demo_address_is_reserved(self, owner, plans, slug):
        with pytest.raises(Conflict) as refused:
            create(owner, slug=slug)

        assert refused.value.code == "hubs.slug_reserved"
        assert not Hub.objects.exists()

    @pytest.mark.parametrize(
        "name",
        ["__", "a_", "x--y", "Ñandú  café", "xn--bar", "-Bar-", "Bar__Manolo", "_-_-_"],
    )
    def test_every_proposed_address_is_one_the_hub_accepts(
        self, owner, plans, name, settings
    ):
        settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}  # production's rule

        slug = create(owner, name=name).slug

        assert validate_hub_slug(slug) == slug

    @pytest.mark.parametrize(
        "slug, says",
        [
            ("ab", "at least 3"),
            ("xn--bar", "xn--"),
            ("bar_manolo", "lowercase letters, digits and hyphens"),
        ],
    )
    def test_a_chosen_address_says_what_is_wrong_with_it(
        self, owner, plans, settings, slug, says
    ):
        settings.LIVE = {**settings.LIVE, "hub_slug_min_length": 3}

        with pytest.raises(InvalidPayload) as refused:
            create(owner, slug=slug)

        assert says in refused.value.fields["slug"]


class TestTheBusinessType:
    def test_it_is_optional(self, owner, plans):
        assert Hub.objects.get(pk=create(owner).id).business_type is None

    def test_answering_it_stores_it(self, owner, plans):
        bar = BusinessType.objects.create(code="bar", name_en="Bar")

        assert (
            Hub.objects.get(pk=create(owner, business_type="bar").id).business_type
            == bar
        )

    def test_an_unknown_code_does_not_break_the_sign_up(self, owner, plans):
        """The form may be cached with a code the catalog no longer has: the hub is born «not said»."""
        assert (
            Hub.objects.get(
                pk=create(owner, business_type="does-not-exist").id
            ).business_type
            is None
        )

    def test_an_inactive_type_is_not_said_either(self, owner, plans):
        BusinessType.objects.create(code="bar", name_en="Bar", is_active=False)

        assert (
            Hub.objects.get(pk=create(owner, business_type="bar").id).business_type
            is None
        )

    def test_the_retired_peluqueria_code_resolves_to_its_survivor(self, owner, plans):
        hair_salon = BusinessType.objects.create(
            code="hair_salon", name_en="Hair Salon"
        )

        assert (
            Hub.objects.get(
                pk=create(owner, business_type="peluqueria").id
            ).business_type
            == hair_salon
        )


class TestTheCountry:
    def test_it_is_stored_uppercase(self, owner, plans):
        assert (
            Hub.objects.get(
                pk=services.business_create(
                    ctx_for(owner), BusinessCreateIn(name="Bar", country="pt")
                ).id
            ).country
            == "PT"
        )

    def test_a_country_we_do_not_serve_is_refused(self):
        with pytest.raises(Exception) as refused:
            BusinessCreateIn(name="Bar", country="US")

        assert "country" in str(refused.value)

    def test_the_time_zone_follows_the_country(self, owner, plans, make_user):
        assert (
            Hub.objects.get(pk=create(owner, country="PT").id).timezone
            == "Europe/Lisbon"
        )
        spaniard = make_user("spaniard@example.com")
        assert (
            Hub.objects.get(pk=create(spaniard, name="Bar 2", country="ES").id).timezone
            == "Europe/Madrid"
        )


class TestTheFreeQuota:
    def test_a_second_free_business_of_the_same_owner_is_refused(self, owner, plans):
        create(owner)

        with pytest.raises(Conflict) as refused:
            create(owner, name="Second")

        assert refused.value.code == "hubs.free_hub_limit"

    def test_a_refusal_leaves_nothing_behind(self, owner, plans):
        create(owner)
        counts = (
            Hub.objects.count(),
            BillingProfile.objects.count(),
            HubMember.objects.count(),
        )

        with pytest.raises(Conflict):
            create(owner, name="Second")

        assert (
            Hub.objects.count(),
            BillingProfile.objects.count(),
            HubMember.objects.count(),
        ) == counts

    def test_the_quota_is_per_owner_not_per_membership(self, owner, plans, make_user):
        """Being a member of somebody else's free business is no free business of one's own."""
        other = make_user("other@example.com")
        add_member(create_business(other), owner, HubMember.Role.ADMIN)

        assert create(owner).status == "preparing"

    def test_a_deleted_free_business_no_longer_counts(self, owner, plans):
        Hub.objects.filter(pk=create(owner).id).update(status=Hub.Status.DELETING)

        assert create(owner, name="Again").status == "preparing"

    def test_the_quota_comes_from_the_settings(self, owner, plans, settings):
        settings.FREE_HUBS_PER_ACCOUNT = 3
        for name in ("One", "Two", "Three"):
            create(owner, name=name)

        with pytest.raises(Conflict):
            create(owner, name="Four")

    def test_restoring_a_free_business_respects_the_quota(self, owner, plans):
        """Review of L1-A, finding 2: delete a free business, create another, restore the first."""
        first = create_business(owner)
        services.business_delete(
            ctx_for(owner), BusinessDeleteIn(id=first.id, confirm_name="Bar Manolo")
        )
        create(owner, name="Second")

        with pytest.raises(Conflict) as refused:
            services.business_restore(ctx_for(owner), ByIdIn(id=first.id))

        assert refused.value.code == "hubs.free_hub_limit"
        assert Hub.objects.get(pk=first.pk).status == "deleting"

    def test_without_a_free_plan_it_is_an_error_not_a_silent_loop(self, owner, plans):
        Plan.objects.filter(slug="free").update(is_active=False)

        with pytest.raises(OperationError) as refused:
            create(owner)

        assert (refused.value.status, refused.value.code) == (
            503,
            "hubs.free_plan_missing",
        )


def test_a_staff_account_creates_no_business(plans, make_user):
    """The invariant of invitations: the platform's staff and the customers never share an account."""
    staff = make_user("staff@erplora.com", is_staff=True)

    with pytest.raises(Conflict) as refused:
        create(staff)

    assert refused.value.code == "hubs.platform_account"
    assert not Hub.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_sign_ups_at_once_leave_one_free_business(make_user, plans):
    """Review of L1-A, finding 2: two requests of one account, each in its own connection, both
    counting before either wrote. With the account's row locked, the second counts the first."""
    import threading

    from django.db import connections

    ana = make_user("ana@example.com")
    barrier = threading.Barrier(2, timeout=2)
    real = queries.free_hubs_owned
    outcomes = []

    def counted_then_wait(user, excluding=None):
        owned = real(user, excluding=excluding)
        try:
            barrier.wait()  # without the lock both get here with 0; with it, the second never does in time
        except threading.BrokenBarrierError:
            pass
        return owned

    def sign_up(name):
        try:
            outcomes.append(create(ana, name=name).status)
        except Conflict as refused:
            outcomes.append(refused.code)
        except Exception as failed:  # noqa: BLE001 - a thread's error must show in the assertion
            outcomes.append(repr(failed))
        finally:
            connections.close_all()

    original = queries.free_hubs_owned
    queries.free_hubs_owned = counted_then_wait
    try:
        threads = [
            threading.Thread(target=sign_up, args=(name,)) for name in ("One", "Two")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        queries.free_hubs_owned = original

    assert sorted(outcomes) == ["hubs.free_hub_limit", "preparing"]
    assert Hub.objects.count() == 1


def test_an_anonymous_visitor_creates_nothing(plans):
    """Without an account there is no permission: the route answers 401 before (test_api)."""
    with pytest.raises((Unauthorized, PermissionDenied)):
        create(None)

    assert not Hub.objects.exists()


# --- Updating -------------------------------------------------------------------------------------


class TestUpdate:
    def test_the_owner_and_an_admin_change_the_settings(self, business, team):
        for who, name in (("owner", "Bar Manolo SL"), ("admin", "Bar Manolo")):
            services.business_update(
                ctx_for(team[who]), BusinessUpdateIn(id=business.id, name=name)
            )
            business.refresh_from_db()
            assert business.name == name

    def test_only_what_is_sent_changes(self, business, owner):
        services.business_update(
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

        services.business_update(
            ctx_for(owner), BusinessUpdateIn(id=business.id, name="New name")
        )
        business.refresh_from_db()

        assert business.pending_hub_call == "put"

    def test_no_change_owes_nothing(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(pending_hub_call="")

        services.business_update(
            ctx_for(owner), BusinessUpdateIn(id=business.id, name="Bar Manolo")
        )
        business.refresh_from_db()

        assert business.pending_hub_call == ""

    def test_a_new_name_reaches_the_hub(self, business, owner, hub_double, django_capture_on_commit_callbacks):
        """HUBS-F15, trap of ERPlora/saas SAAS_DASHBOARD-F09: the new name never reached the hub (its screen, its
        receipts). Here the registry the Hub keeps is pushed again with it after the COMMIT."""
        with django_capture_on_commit_callbacks(execute=True):
            services.business_update(ctx_for(owner), BusinessUpdateIn(id=business.id, name="Casa Manolo"))

        assert hub_double.registry[str(business.id)]["name"] == "Casa Manolo"

    @pytest.mark.parametrize("name", ["", "   "])
    def test_an_empty_name_is_not_saved(self, client, business, owner, name):
        """HUBS-F15, trap of SAAS_DASHBOARD-F09: the old page saved an empty name."""
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
            services.business_update(
                ctx_for(team[who]), BusinessUpdateIn(id=business.id, name="Mine")
            )

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_somebody_without_access_does_not_even_learn_it_exists(
        self, business, team, who
    ):
        with pytest.raises(NotFound):
            services.business_update(
                ctx_for(team[who]), BusinessUpdateIn(id=business.id, name="Mine")
            )

    def test_a_deleted_business_is_not_changed(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with pytest.raises(Conflict) as refused:
            services.business_update(
                ctx_for(owner), BusinessUpdateIn(id=business.id, name="Mine")
            )

        assert refused.value.code == "hubs.business_deleted"


class TestTheCountryLocksOnceReady:
    """The country is not changed once the business is ready (mockups README §6.21, W-B7: its fiscal series
    and records belong to one country). The SaaS does not see the invoices, which live in the Hub: the lock
    starts when the Hub reports the business ready (``ready_at``), the earliest moment it can invoice."""

    def ready(self, business):
        Hub.objects.filter(pk=business.pk).update(
            ready_at=timezone.now(), status=Hub.Status.ACTIVE
        )

    def test_while_it_is_prepared_the_country_still_changes(self, business, owner):
        services.business_update(
            ctx_for(owner), BusinessUpdateIn(id=business.id, country="PT")
        )

        assert Hub.objects.get(pk=business.pk).country == "PT"

    def test_once_ready_a_new_country_is_refused_and_nothing_changes(
        self, business, owner
    ):
        self.ready(business)

        with pytest.raises(Conflict) as refused:
            services.business_update(
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

        detail = services.business_update(
            ctx_for(owner),
            BusinessUpdateIn(id=business.id, name="Renamed", country="es"),
        )

        assert (detail.name, detail.country) == ("Renamed", "ES")

    def test_the_page_says_whether_the_country_is_locked(self, business, owner):
        before = queries.business_get(
            ctx_for(owner), ByIdIn(id=business.id)
        ).country_locked
        self.ready(business)

        assert (
            before,
            queries.business_get(ctx_for(owner), ByIdIn(id=business.id)).country_locked,
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


# --- Deleting and recovering ----------------------------------------------------------------------


class TestDelete:
    def delete(self, user, hub, name="Bar Manolo"):
        return services.business_delete(
            ctx_for(user), BusinessDeleteIn(id=hub.id, confirm_name=name)
        )

    def test_the_owner_deletes_it_and_the_record_stays(self, business, owner):
        deleted = self.delete(owner, business)
        business.refresh_from_db()

        assert (business.status, deleted.status) == ("deleting", "deleting")
        assert business.deletion_requested_at is not None
        assert deleted.purge_after == business.deletion_requested_at + timedelta(
            days=90
        )

    def test_the_hub_owes_the_deletion(self, business, owner):
        self.delete(owner, business)
        business.refresh_from_db()

        assert business.pending_hub_call == "delete"

    def test_nobody_enters_a_deleted_business(self, business, team):
        self.delete(team["owner"], business)

        assert not HubMembership.objects.filter(hub_slug=business.slug).exists()

    def test_the_name_must_be_typed_again(self, business, owner):
        with pytest.raises(InvalidPayload) as refused:
            self.delete(owner, business, name="Bar")

        assert set(refused.value.fields) == {"confirm_name"}
        business.refresh_from_db()
        assert business.status == "preparing"

    def test_the_name_is_compared_without_case_nor_outer_spaces(self, business, owner):
        assert self.delete(owner, business, name="  bar manolo ").status == "deleting"

    @pytest.mark.parametrize("who", ["admin", "manager", "employee"])
    def test_only_the_owner_deletes(self, business, team, who):
        with pytest.raises(PermissionDenied):
            self.delete(team[who], business)

    def test_deleting_twice_is_a_conflict(self, business, owner):
        self.delete(owner, business)

        with pytest.raises(Conflict) as refused:
            self.delete(owner, business)

        assert refused.value.code == "hubs.business_deleted"

    def test_the_owner_is_told_until_when_it_can_be_recovered(
        self, business, owner, django_capture_on_commit_callbacks, offline_hub
    ):
        with django_capture_on_commit_callbacks(execute=True):
            self.delete(owner, business)
        business.refresh_from_db()

        (message,) = mail.outbox
        assert message.to == ["owner@example.com"]
        with translation.override("es"):
            from django.utils.formats import date_format

            purge = date_format(timezone.localtime(business.purge_after), "DATE_FORMAT")
        assert "Bar Manolo" in message.subject
        assert purge in message.body
        # The account reads Spanish.
        assert "recuperar" in message.body.lower()

    def test_deleting_cancels_the_plan_at_once(self, business, owner, plans):
        """Round 17 §2.11: it comes back on Free."""
        Subscription.objects.filter(hub=business).update(
            plan=Plan.objects.get(slug="standard"), trial_plan=None, status="active"
        )

        self.delete(owner, business)

        subscription = Subscription.objects.get(hub=business)
        assert (
            subscription.plan.slug,
            subscription.trial_plan,
            subscription.status,
        ) == ("free", None, "active")


class TestRestore:
    def deleted(self, business, owner, days_ago=1):
        services.business_delete(
            ctx_for(owner), BusinessDeleteIn(id=business.id, confirm_name=business.name)
        )
        Hub.objects.filter(pk=business.pk).update(
            deletion_requested_at=timezone.now() - timedelta(days=days_ago),
            pending_hub_call="",
        )
        return business

    def test_within_ninety_days_the_owner_gets_it_back(self, business, owner):
        self.deleted(business, owner)
        version = Hub.objects.get(pk=business.pk).state_version

        restored = services.business_restore(ctx_for(owner), ByIdIn(id=business.id))
        business.refresh_from_db()

        assert (restored.status, business.status, business.deletion_requested_at) == (
            "preparing",
            "preparing",
            None,
        )
        assert business.pending_hub_call == "restore"
        assert business.state_version == version + 1
        assert HubMembership.objects.filter(user=owner, hub_slug=business.slug).exists()

    def test_a_business_that_was_ready_comes_back_active(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(
            ready_at=timezone.now(), status=Hub.Status.ACTIVE
        )
        self.deleted(business, owner)

        assert (
            services.business_restore(ctx_for(owner), ByIdIn(id=business.id)).status
            == "active"
        )

    def test_after_ninety_days_it_is_gone(self, business, owner):
        self.deleted(business, owner, days_ago=90)

        with pytest.raises(Conflict) as refused:
            services.business_restore(ctx_for(owner), ByIdIn(id=business.id))

        assert refused.value.code == "hubs.business_purged"

    def test_a_business_that_is_not_deleted_is_not_restored(self, business, owner):
        with pytest.raises(Conflict) as refused:
            services.business_restore(ctx_for(owner), ByIdIn(id=business.id))

        assert refused.value.code == "hubs.business_not_deleted"

    def test_only_the_owner_restores(self, business, team):
        self.deleted(business, team["owner"])

        with pytest.raises(PermissionDenied):
            services.business_restore(ctx_for(team["admin"]), ByIdIn(id=business.id))


# --- Opening --------------------------------------------------------------------------------------


class TestOpen:
    """«Open» (PLAN-SAAS §3.1 step 5): the Hub now binds the jump to the browser with a ``state`` of its
    own, so the panel no longer mints the code. The operation checks the member and the business and
    answers the Hub's start (``/auth/login?next=``), which bounces to ``/hub-login/`` with its ``state``:
    that door mints the code, and asks for the second factor if the account has one."""

    def ready(self, hub):
        Hub.objects.filter(pk=hub.pk).update(
            status=Hub.Status.ACTIVE, ready_at=timezone.now()
        )

    def test_it_answers_the_hubs_start_and_mints_no_code(self, business, owner):
        self.ready(business)

        opened = services.business_open(
            ctx_for(owner), BusinessOpenIn(id=business.id, next="/sales")
        )

        assert opened.url == "http://bar-manolo.localhost:8000/auth/login?next=/sales"
        assert not AuthExchangeCode.objects.exists()

    def test_in_production_it_is_the_businesss_own_host(self, business, owner, settings):
        settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"
        self.ready(business)

        opened = services.business_open(ctx_for(owner), BusinessOpenIn(id=business.id))

        assert opened.url == "https://bar-manolo.erplora.com/auth/login?next=/"

    def test_it_remembers_the_business_last_opened(self, business, owner):
        self.ready(business)

        services.business_open(ctx_for(owner), BusinessOpenIn(id=business.id))

        assert (
            HubMember.objects.get(hub=business, user=owner).last_opened_at is not None
        )

    @pytest.mark.parametrize("who", ["admin", "manager", "employee"])
    def test_every_role_opens(self, business, team, who):
        self.ready(business)

        assert services.business_open(
            ctx_for(team[who]), BusinessOpenIn(id=business.id)
        ).url.endswith("/auth/login?next=/")

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_without_access_there_is_nothing_to_open(self, business, team, who):
        """An invitation is accepted first («Accept and enter»)."""
        self.ready(business)

        with pytest.raises(NotFound):
            services.business_open(ctx_for(team[who]), BusinessOpenIn(id=business.id))

    @pytest.mark.parametrize(
        "status, code",
        [
            ("preparing", "hubs.business_preparing"),
            ("suspended", "hubs.business_suspended"),
            ("deleting", "hubs.business_deleted"),
        ],
    )
    def test_a_business_that_cannot_serve_says_why(self, business, owner, status, code):
        Hub.objects.filter(pk=business.pk).update(status=status)

        with pytest.raises(Conflict) as refused:
            services.business_open(ctx_for(owner), BusinessOpenIn(id=business.id))

        assert refused.value.code == code
        assert HubMember.objects.get(hub=business, user=owner).last_opened_at is None

    def test_a_payment_pending_business_still_opens(self, business, owner):
        """Round 17 §2.10: 7 days of grace with «Open» enabled and a notice."""
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.PAST_DUE)

        assert services.business_open(
            ctx_for(owner), BusinessOpenIn(id=business.id)
        ).url

    def test_the_second_factor_is_asked_where_the_code_is_minted(
        self, business, owner, settings, monkeypatch
    ):
        """``/hub-login/`` sends an account with an authenticator app to confirm it (``reauthenticate``)
        before it mints the code; «Open» no longer refuses it on its own."""
        settings.ACCOUNTS_MFA_ENABLED = True
        self.ready(business)
        from accounts import queries as account_queries

        monkeypatch.setattr(account_queries, "has_totp", lambda user: True)

        assert services.business_open(ctx_for(owner), BusinessOpenIn(id=business.id)).url
        assert not AuthExchangeCode.objects.exists()

    def test_from_the_installed_app_the_jump_carries_the_shell_mark(self, business, owner):
        """HUBS-F12 (HUBS-G71, old saas SAAS_DASHBOARD-F07; PLAN-SAAS bloque 3, PLAN-HUB round 18): the app
        links the till to a hub only when a navigation with ``?shell=1`` leaves an entry page of the SaaS
        (``ERPlora/app`` ``hub_link.rs``), so its «Open» starts the jump with the mark."""
        self.ready(business)

        opened = services.business_open(
            ctx_for(owner), BusinessOpenIn(id=business.id, next="/sales", shell=True)
        )

        assert opened.url == "http://bar-manolo.localhost:8000/auth/login?next=/sales&shell=1"

    def test_the_web_jump_carries_no_shell_mark(self, business, owner):
        self.ready(business)

        assert "shell" not in services.business_open(ctx_for(owner), BusinessOpenIn(id=business.id)).url

    def test_next_is_a_path_of_the_business(self):
        for wrong in ("https://evil.example", "//evil.example", "sales"):
            with pytest.raises(Exception):
                BusinessOpenIn(id="0199a000-0000-7000-8000-000000000000", next=wrong)


# --- Ready ----------------------------------------------------------------------------------------


class TestMarkReady:
    def system(self, hub):
        return services.system_ctx_for(hub.id)

    def test_the_hubs_callback_makes_it_active(self, business):
        ready = services.business_mark_ready(
            self.system(business), MarkReadyIn(id=business.id)
        )
        business.refresh_from_db()

        assert (business.status, ready.status) == ("active", "active")
        assert business.ready_at is not None

    def test_it_is_idempotent(self, business):
        services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))
        first = Hub.objects.get(pk=business.pk).ready_at

        services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert Hub.objects.get(pk=business.pk).ready_at == first

    def test_a_deleted_business_stays_deleted(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert Hub.objects.get(pk=business.pk).status == "deleting"

    def test_a_suspended_business_keeps_its_status(self, business):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED)

        services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert Hub.objects.get(pk=business.pk).status == "suspended"

    def test_only_the_system_marks_a_business_ready(self, business, owner):
        with pytest.raises(PermissionDenied):
            services.business_mark_ready(ctx_for(owner), MarkReadyIn(id=business.id))

    def test_the_owner_is_mailed_once_after_the_commit(
        self, business, owner, mailoutbox, django_capture_on_commit_callbacks
    ):
        """HUBS-F04/HUBS-F07: «your business is ready», once (old saas SAAS_DASHBOARD-F29: «una sola vez»),
        and never inside the transaction that marks it ready."""
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))
        assert mailoutbox == []
        for callback in callbacks:
            callback()
        with django_capture_on_commit_callbacks(execute=True):
            services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert [message.to for message in mailoutbox] == [[owner.email]]

    def test_a_business_that_does_not_open_is_not_announced(
        self, business, mailoutbox, django_capture_on_commit_callbacks
    ):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with django_capture_on_commit_callbacks(execute=True):
            services.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert mailoutbox == []

    def test_the_system_acts_in_the_owners_channel(self, business, owner):
        """Its event reaches the owner's live lists (scope = the user, plan §3)."""
        assert self.system(business).scope.key == str(owner.pk)


# --- The state version ----------------------------------------------------------------------------


def test_every_change_of_the_snapshot_moves_the_version_forward(business, team, plans):
    """The Hub ignores an older snapshot (§2.2): ours must grow with every change it carries."""
    versions = [Hub.objects.get(pk=business.pk).state_version]
    services.bump_state(business.id)
    versions.append(Hub.objects.get(pk=business.pk).state_version)
    services.business_delete(
        ctx_for(team["owner"]),
        BusinessDeleteIn(id=business.id, confirm_name="Bar Manolo"),
    )
    services.business_restore(ctx_for(team["owner"]), ByIdIn(id=business.id))
    versions.append(Hub.objects.get(pk=business.pk).state_version)

    assert versions == sorted(set(versions))
