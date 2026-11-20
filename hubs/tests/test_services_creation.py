"""Creating a business, ``hubs.business.create``: the sign-up from one question.

A duplicate, reserved or emoji name never blocks it; a second free hub is refused; a missing Free plan is an
error, not a loop. The business type is optional, an unknown code is «not said» and a retired code resolves to
its survivor; the country is stored uppercase and one we do not serve is refused. A local Free subscription
without Stripe, the creator is the owner member, born with the business, the quota is per account and a refusal
leaves nothing behind.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.models import OutboxEvent
from live.slugs import validate_hub_slug
from live.errors import (
    Conflict,
    InvalidPayload,
    OperationError,
    PermissionDenied,
    Unauthorized,
)

from hubs import events, queries, services
from hubs.models import BillingProfile, BusinessType, Hub, HubMember, Plan, Subscription
from hubs.schemas.businesses import BusinessDeleteIn
from hubs.schemas.common import ByIdIn
from hubs.schemas.signup import BusinessCreateIn
from hubs.tests.conftest import add_member, create_business, ctx_for, role_on

pytestmark = pytest.mark.django_db


def create(user, **data):
    return services.creation.business_create(
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
        """No plan of the catalogue carries a trial; the Free plan is the way in."""
        subscription = Subscription.objects.get(hub=create_business(owner))

        assert (subscription.plan.slug, subscription.trial_plan, subscription.trial_end) == ("free", None, None)
        assert subscription.status != "trialing"

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one by default)
    def test_free_is_born_with_the_starter_trial(self, owner, plans):
        """Dormant: when staff give Starter a trial, Free is born with its days."""
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
        """The jump reads the business's answered members: the owner is born answered."""
        hub = create_business(owner)

        assert role_on(owner, hub.slug) == "hub_owner"


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

    # slugify() keeps "_", which no DNS label (live.slugs) admits; such an
    # address was stored, the Hub refused its registry forever and nobody could enter or rename it.

    def test_an_underscore_never_reaches_the_address(self, owner, plans):
        assert create(owner, name="Bar_Manolo").slug == "bar-manolo"

    def test_a_name_cut_at_an_underscore_never_ends_in_a_hyphen(self, owner, plans):
        name = "a" * 29 + "_bar"  # cut at 30 characters, the last one is the underscore

        slug = create(owner, name=name).slug

        assert slug == "a" * 29
        assert validate_hub_slug(slug) == slug

    # ``demo-…`` names the demo hubs (live.slugs, ``allow_demo`` only in the Hub's registry). A name like «Demo
    # Bar» would propose ``demo-bar``, which no customer may take, and the address would fall back to
    # ``my-business`` and lose the name: the prefix loses its hyphen instead.

    def test_a_name_that_starts_like_a_demo_keeps_its_words(self, owner, plans):
        assert create(owner, name="Demo Bar").slug == "demobar"

    def test_the_word_demo_alone_gets_room_to_be_an_address(self, owner, plans):
        assert create(owner, name="Demo").slug == "demostore"

    def test_a_second_demo_bar_is_numbered_as_any_other(self, owner, plans, make_user):
        create(owner, name="Demo Bar")

        assert create(make_user("other@example.com"), name="Demo Bar").slug == "demobar-2"

    @pytest.mark.parametrize("name", ["Demo Bar", "demo-store", "DEMO--Tienda", "Demo_Bar"])
    def test_no_proposed_address_is_a_demo_hubs(self, owner, plans, name):
        slug = queries.addresses.free_slug(name)

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
                pk=services.creation.business_create(
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
        """Delete a free business, create another, restore the first."""
        first = create_business(owner)
        services.deletion.business_delete(
            ctx_for(owner), BusinessDeleteIn(id=first.id, confirm_name="Bar Manolo")
        )
        create(owner, name="Second")

        with pytest.raises(Conflict) as refused:
            services.deletion.business_restore(ctx_for(owner), ByIdIn(id=first.id))

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


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_a_staff_account_creates_no_business(plans, make_user, flag):
    """The invariant of invitations: the platform's staff and the customers never share an account. A superuser
    without «staff status» (made by hand in a shell) is the platform's too."""
    staff = make_user("staff@erplora.com", **{flag: True})

    with pytest.raises(Conflict) as refused:
        create(staff)

    assert refused.value.code == "hubs.platform_account"
    assert not Hub.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_two_sign_ups_at_once_leave_one_free_business(make_user, plans):
    """Two requests of one account, each in its own connection, both
    counting before either wrote. With the account's row locked, the second counts the first."""
    import threading

    from django.db import connections

    ana = make_user("ana@example.com")
    barrier = threading.Barrier(2, timeout=2)
    real = queries.signup.free_hubs_owned
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

    original = queries.signup.free_hubs_owned
    queries.signup.free_hubs_owned = counted_then_wait
    try:
        threads = [
            threading.Thread(target=sign_up, args=(name,)) for name in ("One", "Two")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        queries.signup.free_hubs_owned = original

    assert sorted(outcomes) == ["hubs.free_hub_limit", "preparing"]
    assert Hub.objects.count() == 1


def test_an_anonymous_visitor_creates_nothing(plans):
    """Without an account there is no permission: the route answers 401 before (test_api)."""
    with pytest.raises((Unauthorized, PermissionDenied)):
        create(None)

    assert not Hub.objects.exists()
