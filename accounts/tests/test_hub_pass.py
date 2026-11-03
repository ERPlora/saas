"""``/hub-pass/?pass=<pass>``: the way back from a business to erplora.com with a one-time pass (ACCOUNTS-F29, BASE-F11
of the Hub; saas#190).

The Hub signs the pass as these tests do (``mint``): ``django.core.signing.dumps`` of ``{"user", "hub", "next",
"nonce"}`` keyed with ``INTERNAL_SHARED_SECRET`` and salted with ``erplora.hub-pass.v1``. erplora.com accepts it for a
minute and once, opens the session of that account only if it is a member of that business, and lands on the plan or
on the business. Anything else opens nothing and lands on ``/login/error?code=…``.
"""

import time
import uuid
from datetime import date
from unittest import mock
from urllib.parse import quote

import pytest
from django.contrib.auth import SESSION_KEY, get_user_model
from django.core import signing
from django.test import Client

from accounts import hub_pass, services
from accounts.models import AuthExchangeCode
from accounts.tests.conftest import AUTHENTICATION_RECORDS
from hubs.models import HubMember
from hubs.tests.conftest import add_member, create_business, make_user, plans  # noqa: F401 - the fixtures

pytestmark = pytest.mark.django_db

HUB_PASS = "/hub-pass/"
SALT = "erplora.hub-pass.v1"
SECRET = "the-secret-the-hub-and-the-saas-share"
PREVIOUS = "the-secret-before-the-rotation"
#: Versions of the terms and the privacy policy older than today's.
OLD = date(2020, 1, 1)


@pytest.fixture(autouse=True)
def shared_secret(settings):
    settings.INTERNAL_SHARED_SECRET = SECRET
    settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
    settings.HUB_PASS_MAX_AGE_SECONDS = 60


@pytest.fixture
def business(plans, ana):  # noqa: F811 - the plans fixture
    return create_business(ana, name="Bar Manolo")


def mint(account, slug: str, next_: str = "plan", *, key: str = SECRET, salt: str = SALT, age: int = 0, **change) -> str:
    """The pass as the Hub signs it, ``age`` seconds ago; ``change`` overrides any of its fields."""
    payload = {
        "user": str(account.pk) if hasattr(account, "pk") else account,
        "hub": slug,
        "next": next_,
        "nonce": uuid.uuid4().hex,
    }
    payload.update(change)
    with mock.patch("django.core.signing.time.time", return_value=time.time() - age):
        return signing.dumps(payload, key=key, salt=salt)


def follow(client: Client, token: str):
    return client.get(HUB_PASS, {"pass": token})


def signed_in(client: Client):
    """The account of ``client``'s session, or ``None``."""
    pk = client.session.get(SESSION_KEY)
    return None if pk is None else get_user_model().objects.get(pk=pk)


def plan_page(hub) -> str:
    return f"/dashboard/store/plans?business={hub.id}"


def business_page(hub) -> str:
    return f"/dashboard/businesses/{hub.id}"


def expired(next_path: str) -> str:
    return "/login/error?code=pass_expired&next=" + quote(next_path, safe="/")


INVALID = "/login/error?code=invalid_pass"


class TestAValidPass:
    def test_it_opens_the_session_of_the_account_and_lands_on_the_plan_of_the_business(self, client, ana, business):
        response = follow(client, mint(ana, business.slug, "plan"))

        assert response.status_code == 302
        assert response.url == plan_page(business)
        assert signed_in(client) == ana

    def test_the_business_lands_on_the_business_in_the_panel(self, client, ana, business):
        response = follow(client, mint(ana, business.slug, "business"))

        assert response.url == business_page(business)
        assert signed_in(client) == ana

    def test_any_member_enters_not_only_the_owner(self, client, ana, business, make_user):
        employee = make_user("eva@example.com")
        add_member(business, employee, HubMember.Role.EMPLOYEE)

        response = follow(client, mint(employee, business.slug))

        assert response.url == plan_page(business)
        assert signed_in(client) == employee

    def test_the_answer_is_never_cached_and_leaks_no_referrer(self, client, ana, business):
        response = follow(client, mint(ana, business.slug))

        assert "no-store" in response["Cache-Control"]
        assert response["Referrer-Policy"] == "no-referrer"

    def test_a_pass_of_59_seconds_still_opens(self, client, ana, business):
        response = follow(client, mint(ana, business.slug, age=59))

        assert response.url == plan_page(business)
        assert signed_in(client) == ana

    def test_a_pass_signed_with_the_previous_secret_opens_during_a_rotation(self, client, settings, ana, business):
        settings.INTERNAL_SHARED_SECRET_PREVIOUS = PREVIOUS

        response = follow(client, mint(ana, business.slug, key=PREVIOUS))

        assert response.url == plan_page(business)
        assert signed_in(client) == ana

    def test_the_session_it_opens_passed_no_sign_in_of_allauth(self, client, ana, business):
        # No record of a password, a code or a second factor: whatever asks for one asks for it again.
        follow(client, mint(ana, business.slug))

        assert AUTHENTICATION_RECORDS not in client.session

    def test_the_session_it_opens_shows_in_the_active_sessions_of_the_account(self, client, ana, business):
        # Account → Security → Active sessions: whoever finds it there can end it, as any other.
        from allauth.usersessions.models import UserSession

        follow(client, mint(ana, business.slug))

        assert UserSession.objects.filter(user=ana, session_key=client.session.session_key).exists()

    def test_it_accepts_no_terms_on_the_way(self, client, ana, business):
        # Only the sign-in shows «By continuing you agree…»: a pass shows nothing, so it records nothing.
        get_user_model().objects.filter(pk=ana.pk).update(terms_version=OLD, privacy_version=OLD, terms_accepted_at=None)

        follow(client, mint(ana, business.slug))

        ana.refresh_from_db()
        assert (ana.terms_version, ana.privacy_version, ana.terms_accepted_at) == (OLD, OLD, None)


class TestOnlyOnce:
    def test_the_same_pass_twice_opens_nothing_the_second_time(self, ana, business):
        token = mint(ana, business.slug)
        follow(Client(), token)
        other_browser = Client()

        response = follow(other_browser, token)

        assert response.url == expired(plan_page(business))
        assert signed_in(other_browser) is None

    def test_spending_it_leaves_a_used_row_that_no_jump_to_a_hub_redeems(self, client, ana, business):
        token = mint(ana, business.slug)
        nonce = signing.loads(token, key=SECRET, salt=SALT)["nonce"]

        follow(client, token)

        row = AuthExchangeCode.objects.get(audience=hub_pass.AUDIENCE)
        assert row.code_hash == AuthExchangeCode.hash_code(f"{hub_pass.AUDIENCE}:{nonce}")
        assert (row.user, row.hub_slug) == (ana, business.slug)
        assert row.used_at is not None
        assert row.expires_at >= row.used_at + hub_pass.lifetime()
        for audience in (AuthExchangeCode.HUB_SESSION_AUDIENCE, AuthExchangeCode.HUB_ADMIN_AUDIENCE):
            with pytest.raises(services.InvalidCode):
                services.redeem_code(nonce, business.slug, audience=audience)

    def test_a_pass_spent_by_this_same_account_takes_it_on_where_it_was_going(self, client, ana, business):
        # The browser's back button or a reload: the session is already theirs, so nothing new opens.
        token = mint(ana, business.slug)
        follow(client, token)
        session_key = client.session.session_key

        response = follow(client, token)

        assert response.url == plan_page(business)
        assert (signed_in(client), client.session.session_key) == (ana, session_key)

    def test_a_fresh_pass_of_the_account_already_signed_in_is_spent_without_a_new_session(self, client, ana, business):
        client.force_login(ana)
        session_key = client.session.session_key
        token = mint(ana, business.slug)

        response = follow(client, token)

        assert response.url == plan_page(business)
        assert client.session.session_key == session_key
        assert follow(Client(), token).url == expired(plan_page(business))


class TestExpired:
    def test_a_pass_of_61_seconds_opens_nothing(self, client, ana, business):
        response = follow(client, mint(ana, business.slug, age=61))

        assert response.url == expired(plan_page(business))
        assert signed_in(client) is None

    def test_an_expired_pass_is_not_spent(self, client, ana, business):
        follow(client, mint(ana, business.slug, age=61))

        assert not AuthExchangeCode.objects.filter(audience=hub_pass.AUDIENCE).exists()

    def test_the_lifetime_is_the_setting(self, client, settings, ana, business):
        settings.HUB_PASS_MAX_AGE_SECONDS = 30

        response = follow(client, mint(ana, business.slug, age=31))

        assert response.url == expired(plan_page(business))

    def test_an_expired_pass_of_the_account_already_signed_in_takes_it_on_where_it_was_going(self, client, ana, business):
        # A reload of the tab a while later: the session is theirs already, so there is nothing to open.
        client.force_login(ana)
        session_key = client.session.session_key

        response = follow(client, mint(ana, business.slug, "business", age=61))

        assert response.url == business_page(business)
        assert client.session.session_key == session_key
        assert not AuthExchangeCode.objects.filter(audience=hub_pass.AUDIENCE).exists()

    def test_another_account_signed_in_keeps_its_session(self, client, ana, business, make_user):
        bea = make_user("bea@example.com")
        client.force_login(bea)

        response = follow(client, mint(ana, business.slug, age=61))

        assert response.url == expired(plan_page(business))
        assert signed_in(client) == bea


class TestBadlySigned:
    @pytest.mark.parametrize(
        ("key", "salt"),
        [
            ("another-secret", SALT),
            (SECRET, "another-salt"),
            (SECRET, "django.core.signing"),
        ],
        ids=["another-key", "another-salt", "no-salt"],
    )
    def test_a_pass_not_signed_as_the_hub_signs_it_opens_nothing(self, client, ana, business, key, salt):
        response = follow(client, mint(ana, business.slug, key=key, salt=salt))

        assert response.url == INVALID
        assert signed_in(client) is None

    def test_a_pass_with_one_character_changed_opens_nothing(self, client, ana, business):
        token = mint(ana, business.slug)
        changed = ("B" if token[0] == "A" else "A") + token[1:]

        response = follow(client, changed)

        assert response.url == INVALID
        assert signed_in(client) is None

    def test_the_previous_secret_opens_nothing_once_the_rotation_ended(self, client, ana, business):
        response = follow(client, mint(ana, business.slug, key=PREVIOUS))

        assert response.url == INVALID

    def test_without_a_shared_secret_nothing_opens_not_even_with_the_secret_key(self, client, settings, ana, business):
        settings.INTERNAL_SHARED_SECRET = ""

        response = follow(client, mint(ana, business.slug, key=settings.SECRET_KEY))

        assert response.url == INVALID
        assert signed_in(client) is None

    @pytest.mark.parametrize("query", [{}, {"pass": ""}, {"pass": "not-a-pass"}, {"pass": "a:b:c"}])
    def test_no_pass_or_garbage_opens_nothing(self, client, query):
        response = client.get(HUB_PASS, query)

        assert response.url == INVALID
        assert signed_in(client) is None

    def test_only_get(self, client, ana, business):
        response = client.post(HUB_PASS, {"pass": mint(ana, business.slug)})

        assert response.status_code == 405
        assert signed_in(client) is None


class TestWhatThePassSays:
    @pytest.mark.parametrize(
        "next_",
        ["", "account", "billing", "/dashboard/account", "https://evil.example/", "//evil.example/", None, 1],
    )
    def test_a_next_outside_the_list_opens_nothing(self, client, ana, business, next_):
        response = follow(client, mint(ana, business.slug, next_))

        assert response.url == INVALID
        assert signed_in(client) is None

    @pytest.mark.parametrize(
        "change",
        [
            {"nonce": ""},
            {"nonce": "short"},
            {"nonce": "x" * 129},
            {"nonce": "has spaces in the nonce!!"},
            {"nonce": 12345678901234567890},
            {"hub": "hubs"},
            {"hub": "www"},
            {"hub": "Not A Slug"},
            {"hub": None},
            {"user": "not-a-uuid"},
            {"user": None},
        ],
        ids=[
            "empty-nonce",
            "short-nonce",
            "long-nonce",
            "nonce-chars",
            "nonce-number",
            "platform-host",
            "reserved-slug",
            "bad-slug",
            "no-hub",
            "bad-user",
            "no-user",
        ],
    )
    def test_a_malformed_pass_opens_nothing(self, client, ana, business, change):
        response = follow(client, mint(ana, business.slug, **change))

        assert response.url == INVALID
        assert signed_in(client) is None

    @pytest.mark.parametrize("missing", ["user", "hub", "next", "nonce"])
    def test_a_pass_missing_a_field_opens_nothing(self, client, ana, business, missing):
        payload = {"user": str(ana.pk), "hub": business.slug, "next": "plan", "nonce": uuid.uuid4().hex}
        del payload[missing]

        response = follow(client, signing.dumps(payload, key=SECRET, salt=SALT))

        assert response.url == INVALID

    def test_a_pass_that_is_no_object_opens_nothing(self, client):
        response = follow(client, signing.dumps(["user", "hub"], key=SECRET, salt=SALT))

        assert response.url == INVALID


class TestOnlyAMember:
    def not_a_member(self, slug: str) -> str:
        return f"/login/error?code=not_a_member&hub={slug}"

    def test_an_account_that_is_no_member_of_that_business_opens_nothing(self, client, business, make_user):
        stranger = make_user("stranger@example.com")

        response = follow(client, mint(stranger, business.slug))

        assert response.url == self.not_a_member(business.slug)
        assert signed_in(client) is None

    def test_a_member_of_another_business_opens_nothing_on_this_one(self, client, ana, business, make_user):
        bea = make_user("bea@example.com")
        other = create_business(bea, name="Frutería Bea")

        response = follow(client, mint(ana, other.slug))

        assert response.url == self.not_a_member(other.slug)
        assert signed_in(client) is None

    def test_a_member_of_a_business_whose_address_contains_this_one_opens_nothing(self, client, business, make_user):
        """Looking the business up by its address finds «bar-manolo-2» too: only the exact one counts."""
        bea = make_user("bea@example.com")
        lookalike = create_business(bea, name="Bar Manolo")
        assert lookalike.slug != business.slug and business.slug in lookalike.slug

        response = follow(client, mint(bea, business.slug))

        assert response.url == self.not_a_member(business.slug)
        assert signed_in(client) is None

    def test_an_invitation_not_accepted_yet_opens_nothing(self, client, business, make_user):
        invited = make_user("invited@example.com")
        add_member(business, invited, HubMember.Role.EMPLOYEE, accepted=False)

        response = follow(client, mint(invited, business.slug))

        assert response.url == self.not_a_member(business.slug)

    def test_a_business_that_does_not_exist_opens_nothing(self, client, ana, business):
        response = follow(client, mint(ana, "no-such-business"))

        assert response.url == self.not_a_member("no-such-business")
        assert signed_in(client) is None

    def test_an_account_switched_off_opens_nothing(self, client, ana, business):
        get_user_model().objects.filter(pk=ana.pk).update(is_active=False)

        response = follow(client, mint(ana, business.slug))

        assert response.url == self.not_a_member(business.slug)
        assert signed_in(client) is None

    def test_an_account_that_no_longer_exists_opens_nothing(self, client, business):
        response = follow(client, mint(str(uuid.uuid7()), business.slug))

        assert response.url == self.not_a_member(business.slug)

    @pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
    def test_an_account_of_the_staff_never_gets_a_session_from_a_pass(self, client, ana, business, flag):
        get_user_model().objects.filter(pk=ana.pk).update(**{flag: True})

        response = follow(client, mint(ana, business.slug))

        assert response.url == self.not_a_member(business.slug)
        assert signed_in(client) is None

    def test_a_refused_pass_is_not_spent(self, client, business, make_user):
        stranger = make_user("stranger@example.com")

        follow(client, mint(stranger, business.slug))

        assert not AuthExchangeCode.objects.filter(audience=hub_pass.AUDIENCE).exists()


class TestAnotherAccountSignedIn:
    def test_a_valid_pass_signs_in_whoever_tapped_the_button_in_the_business(self, client, ana, business, make_user):
        # A shared browser: the account that tapped «Upgrade plan» in the business is the one that goes on.
        bea = make_user("bea@example.com")
        client.force_login(bea)

        response = follow(client, mint(ana, business.slug))

        assert response.url == plan_page(business)
        assert signed_in(client) == ana


class TestTheAddress:
    def test_without_the_slash_it_goes_to_the_route_keeping_the_pass(self, client, ana, business):
        token = mint(ana, business.slug)

        response = client.get("/hub-pass", {"pass": token})

        assert response.status_code == 301
        assert response.url.startswith("/hub-pass/?pass=")


class TestTwoAtOnce:
    @pytest.mark.django_db(transaction=True)
    def test_two_browsers_following_the_same_pass_at_once_open_one_session_only(self, ana, business):
        """Two redemptions of one pass racing each other: exactly one opens a session; the other lands on expired."""
        import threading

        from django.db import connection

        token = mint(ana, business.slug)
        ready = threading.Barrier(2)
        results: dict[int, tuple[str, object]] = {}

        def race(index: int) -> None:
            browser = Client()
            try:
                ready.wait(timeout=10)
                response = follow(browser, token)
                results[index] = (response.url, signed_in(browser))
            finally:
                connection.close()

        threads = [threading.Thread(target=race, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(results.values(), key=lambda outcome: outcome[0]) == [
            (plan_page(business), ana),
            (expired(plan_page(business)), None),
        ]
        assert AuthExchangeCode.objects.filter(audience=hub_pass.AUDIENCE).count() == 1
