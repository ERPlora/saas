"""The reads of the panel: ``hubs.business.list`` (the Businesses page and the launcher), ``hubs.business.get`` (a
business's page) and ``hubs.address.propose`` (the address proposed while the name is typed).

Ported from ERPlora/saas (origin/develop), from views to queries: ``hubs/main/tests/test_api.py``
(only one's own businesses; a stranger gets 404), ``test_business_selector`` (one row per business,
only mine, any role is enough, a deleted one is not listed), ``test_last_business`` (the last opened
first, then by name; a revoked membership or a gone business is forgotten),
``test_shell_create_address_proposal`` (a taken name proposes the free address),
``dashboard/overview/tests/test_api.py`` (what survives as a list: an account with no business, with
several) and ``test_hub_card_status_is_translated`` (the status reads in the account's language).
Dropped with their reason: KPIs, activity, servers, metrics and the htmx cards (round 17 §2.3).
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from live.errors import NotFound, PermissionDenied

from accounts.models import HubMembership
from hubs import queries
from hubs.models import Hub, HubMember, Subscription
from hubs.schemas import AddressProposeIn, BusinessListIn, ByIdIn
from hubs.tests.conftest import add_member, create_business, ctx_for

pytestmark = pytest.mark.django_db


def business_list(user, language="en", **params):
    return queries.business_list(
        ctx_for(user, language), BusinessListIn(**params)
    ).model_dump(mode="json")


def names(page):
    return [row["name"] for row in page["rows"]]


class TestMyBusinesses:
    def test_an_account_without_businesses_lists_none(self, owner):
        assert business_list(owner) == {
            "rows": [],
            "total": 0,
            "limit": 50,
            "offset": 0,
            "invitations": [],
            "ownership_offers": [],
            "free_business": None,
        }

    def test_one_row_per_business_with_what_the_table_shows(self, business, owner):
        (row,) = business_list(owner)["rows"]

        assert row["name"] == "Bar Manolo"
        assert (row["slug"], row["host"]) == ("bar-manolo", "bar-manolo.localhost:8000")
        assert (row["status"], row["role"], row["plan"]) == (
            "preparing",
            "hub_owner",
            {"slug": "free", "name": "Free"},
        )
        assert (row["can_open"], row["open_blocked_reason"]) == (False, "preparing")

    def test_only_mine_with_any_role(self, business, team, make_user):
        create_business(make_user("lola@example.com"), name="Café Lola")

        assert names(business_list(team["employee"])) == ["Bar Manolo"]
        assert names(business_list(team["stranger"])) == []

    def test_an_invitation_is_not_a_business_yet(self, business, team):
        page = business_list(team["invitee"])

        assert page["rows"] == []
        assert [invitation["hub"]["name"] for invitation in page["invitations"]] == [
            "Bar Manolo"
        ]

    def test_the_last_opened_first_then_by_name(
        self, owner, plans, make_user, settings
    ):
        settings.FREE_HUBS_PER_ACCOUNT = 5
        for name in ("Zeta", "Alfa", "Beta"):
            create_business(owner, name=name)
        HubMember.objects.filter(hub__name="Beta").update(
            last_opened_at=timezone.now() - timedelta(days=2)
        )
        HubMember.objects.filter(hub__name="Zeta").update(last_opened_at=timezone.now())

        assert names(business_list(owner)) == ["Zeta", "Beta", "Alfa"]

    def test_a_deleted_business_stays_listed_to_recover_it(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(
            status=Hub.Status.DELETING, deletion_requested_at=timezone.now()
        )

        (row,) = business_list(owner)["rows"]

        assert (row["status"], row["can_open"], row["open_blocked_reason"]) == (
            "deleting",
            False,
            "deleting",
        )
        assert row["purge_after"] is not None

    def test_a_purged_business_is_gone(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

        assert business_list(owner)["rows"] == []

    @pytest.mark.parametrize(
        "status, can_open", [("active", True), ("past_due", True), ("suspended", False)]
    )
    def test_what_opens(self, business, owner, status, can_open):
        Hub.objects.filter(pk=business.pk).update(status=status)

        assert business_list(owner)["rows"][0]["can_open"] is can_open

    def test_a_search_by_name_or_address(self, owner, plans, settings):
        settings.FREE_HUBS_PER_ACCOUNT = 5
        create_business(owner, name="Bar Manolo")
        create_business(owner, name="Peluquería Ana")

        assert names(business_list(owner, search="pelu")) == ["Peluquería Ana"]
        assert names(business_list(owner, search="bar-man")) == ["Bar Manolo"]

    def test_it_is_paginated(self, owner, plans, settings):
        settings.FREE_HUBS_PER_ACCOUNT = 5
        for name in ("A1", "A2", "A3"):
            create_business(owner, name=name)

        page = business_list(owner, limit=2, offset=1)

        assert (names(page), page["total"]) == (["A2", "A3"], 3)

    def test_a_limit_over_one_hundred_is_refused(self):
        with pytest.raises(Exception):
            BusinessListIn(limit=101)

    def test_the_status_and_the_role_read_in_the_accounts_language(
        self, business, owner
    ):
        (row,) = business_list(owner, language="es")["rows"]

        assert (row["status_label"], row["role_label"]) == ("Preparando", "Propietario")


class TestTheFreeQuotaBeforeTheForm:
    """Audit 2 S-02: «Create business» says the one-Free-business limit (ADR-0154) before the form, naming the
    Free business that fills it and offering to change its plan; the list says which one."""

    def test_an_account_whose_free_business_fills_the_quota_is_told_which(self, business, owner):
        assert business_list(owner)["free_business"] == {
            "id": str(business.id),
            "slug": "bar-manolo",
            "name": "Bar Manolo",
        }

    def test_a_paying_or_deleted_business_leaves_room_for_a_free_one(self, business, owner, plans):
        from hubs.models import Plan

        Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="starter"))
        assert business_list(owner)["free_business"] is None

        Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="free"))
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)
        assert business_list(owner)["free_business"] is None

    def test_a_free_business_of_somebody_else_fills_nothing(self, business, team):
        assert business_list(team["admin"])["free_business"] is None

    def test_the_quota_comes_from_the_settings(self, business, owner, settings):
        settings.FREE_HUBS_PER_ACCOUNT = 2

        assert business_list(owner)["free_business"] is None


class TestOneBusiness:
    def test_the_owner_sees_everything_and_may_do_everything(self, business, owner):
        detail = queries.business_get(
            ctx_for(owner), ByIdIn(id=business.id)
        ).model_dump(mode="json")

        assert (
            detail["name"],
            detail["country"],
            detail["timezone"],
            detail["language"],
        ) == ("Bar Manolo", "ES", "Europe/Madrid", "es")
        assert detail["plan"] == {"slug": "free", "name": "Free"}
        assert detail["trial_plan"] == {"slug": "starter", "name": "Starter"}
        assert detail["trial_end"] is not None
        assert detail["seats"] == {"used": 1, "limit": None}
        assert detail["can"] == {
            "open": False,
            "manage": True,
            "manage_members": True,
            "manage_settings": True,
            "manage_billing": True,
            "transfer": True,
            "restore": False,
            "delete": True,
        }
        assert detail["country_locked"] is False

    def test_an_admin_manages_the_team_and_the_settings_only(self, business, team):
        can = queries.business_get(ctx_for(team["admin"]), ByIdIn(id=business.id)).can

        assert (
            can.manage_members,
            can.manage_settings,
            can.manage_billing,
            can.transfer,
            can.delete,
        ) == (True, True, False, False, False)

    @pytest.mark.parametrize("who", ["manager", "employee"])
    def test_a_manager_or_an_employee_only_opens_it(self, business, team, who):
        with pytest.raises(PermissionDenied):
            queries.business_get(ctx_for(team[who]), ByIdIn(id=business.id))

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_without_access_it_does_not_exist(self, business, team, who):
        with pytest.raises(NotFound):
            queries.business_get(ctx_for(team[who]), ByIdIn(id=business.id))

    def test_after_the_trial_the_free_plans_cap_shows(self, business, owner):
        Subscription.objects.filter(hub=business).update(
            trial_end=timezone.now() - timedelta(seconds=1)
        )

        detail = queries.business_get(ctx_for(owner), ByIdIn(id=business.id))

        assert (detail.trial_plan, detail.seats.limit) == (None, 3)

    def test_a_purged_business_is_not_found(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETED)

        with pytest.raises(NotFound):
            queries.business_get(ctx_for(owner), ByIdIn(id=business.id))


class TestTheProposedAddress:
    def propose(self, user, name):
        return queries.address_propose(
            ctx_for(user), AddressProposeIn(name=name)
        ).model_dump()

    def test_typing_the_name_proposes_the_address(self, owner, plans):
        assert self.propose(owner, "Peluquería Ana") == {
            "slug": "peluqueria-ana",
            "host": "peluqueria-ana.localhost:8000",
        }

    def test_a_taken_name_proposes_the_free_address(self, business, owner):
        assert self.propose(owner, "Bar Manolo")["slug"] == "bar-manolo-2"

    def test_an_address_held_by_an_older_hub_is_skipped(self, owner, plans):
        HubMembership.objects.create(
            user=owner, hub_slug="peluqueria-ana", role="hub_owner"
        )

        assert self.propose(owner, "Peluquería Ana")["slug"] == "peluqueria-ana-2"

    def test_a_reserved_name_proposes_a_legal_address(self, owner, plans):
        assert self.propose(owner, "Admin")["slug"] == "admin-store"


def test_a_second_membership_lists_the_business_of_somebody_else(
    business, team, make_user
):
    lola = make_user("lola@example.com")
    other = create_business(lola, name="Café Lola")
    add_member(other, team["owner"], HubMember.Role.MANAGER)

    rows = business_list(team["owner"])["rows"]

    assert [(row["name"], row["role"]) for row in rows] == [
        ("Bar Manolo", "hub_owner"),
        ("Café Lola", "hub_manager"),
    ]


# --- What a business allows, computed by the server (the list stops deducing it from the role) -----

ACTIVE, PREPARING, SUSPENDED, PAST_DUE, DELETING = "active", "preparing", "suspended", "past_due", "deleting"
#: ``(open, manage, restore, delete)`` by status and role: «Open» for every role while it serves,
#: «Manage» for the owner and the administrators while it is not deleted, «Recover» and «Delete»
#: only for the owner, «Recover» only while deleted and within its 90 days.
ALLOWED = {
    ACTIVE: {"owner": (1, 1, 0, 1), "admin": (1, 1, 0, 0), "manager": (1, 0, 0, 0), "employee": (1, 0, 0, 0)},
    PAST_DUE: {"owner": (1, 1, 0, 1), "admin": (1, 1, 0, 0), "manager": (1, 0, 0, 0), "employee": (1, 0, 0, 0)},
    PREPARING: {"owner": (0, 1, 0, 1), "admin": (0, 1, 0, 0), "manager": (0, 0, 0, 0), "employee": (0, 0, 0, 0)},
    SUSPENDED: {"owner": (0, 1, 0, 1), "admin": (0, 1, 0, 0), "manager": (0, 0, 0, 0), "employee": (0, 0, 0, 0)},
    DELETING: {"owner": (0, 0, 1, 0), "admin": (0, 0, 0, 0), "manager": (0, 0, 0, 0), "employee": (0, 0, 0, 0)},
}


def set_status(hub, status):
    deleted_at = timezone.now() - timedelta(days=1) if status == DELETING else None
    Hub.objects.filter(pk=hub.pk).update(status=status, deletion_requested_at=deleted_at)


def row_of(user, hub):
    return next(row for row in business_list(user)["rows"] if row["id"] == str(hub.id))


class TestWhatABusinessAllows:
    @pytest.mark.parametrize("status", list(ALLOWED))
    @pytest.mark.parametrize("who", ["owner", "admin", "manager", "employee"])
    def test_each_row_says_what_its_buttons_do(self, business, team, status, who):
        set_status(business, status)

        can = row_of(team[who], business)["can"]

        expected = dict(zip(("open", "manage", "restore", "delete"), map(bool, ALLOWED[status][who])))
        assert can == expected

    @pytest.mark.parametrize("status", list(ALLOWED))
    @pytest.mark.parametrize("who", ["owner", "admin"])
    def test_the_page_says_the_same_as_its_row(self, business, team, status, who):
        set_status(business, status)

        detail = queries.business_get(ctx_for(team[who]), ByIdIn(id=business.id)).model_dump()["can"]

        assert {key: detail[key] for key in ("open", "manage", "restore", "delete")} == row_of(team[who], business)["can"]

    def test_a_deleted_business_takes_no_change_from_its_page(self, business, team):
        """Every write on it answers 409 until it is recovered: no button of the page would work."""
        set_status(business, DELETING)

        can = queries.business_get(ctx_for(team["owner"]), ByIdIn(id=business.id)).can

        assert (can.manage_members, can.manage_settings, can.transfer, can.delete, can.restore) == (
            False,
            False,
            False,
            False,
            True,
        )

    def test_past_its_90_days_it_cannot_be_recovered(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(
            status=DELETING, deletion_requested_at=timezone.now() - timedelta(days=91)
        )

        assert row_of(owner, business)["can"]["restore"] is False

    def test_the_row_over_http(self, client, business, team):
        client.force_login(team["admin"])

        rows = client.get("/api/hubs/businesses", HTTP_HOST="localhost:8001").json()["rows"]

        assert rows[0]["can"] == {"open": False, "manage": True, "restore": False, "delete": False}
