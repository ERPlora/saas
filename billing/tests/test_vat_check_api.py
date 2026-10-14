"""Checking a VAT number in VIES from the panel (``POST /api/billing/vat-check``) and from the admin.

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_vat_check_api.py`` (origin/develop, 27 tests),
whose ``/api/v1/fiscal/vat-checks/`` was ERPlora support's lever («ask VIES again»). In the new panel the
same check is what the create-business and billing-profile forms ask before paying (the old form's
``check_vat_htmx``), so the operation ``billing.vat_check.run`` is open to every signed-in account and
answers the verdict that will price the sale: a current proof is reused, anything else is asked again.
The properties that hold, each pinned below:

* every query is a NEW row, never an UPDATE: the history is the proof;
* no fiscal rule changes: only ``reverse_charge: true`` invoices without VAT, and a ``valid: true``
  without a consultation number is still ``unavailable``;
* VIES down is a 200 with ``status: unavailable``, never a 5xx: it is an answer, not a fault;
* one per-person budget (``VAT_CHECK_RATE``) for every door that spends a query, the panel's and the
  admin's «Check now in VIES»: each query is a request to the Commission under OUR requester number;
* the admin action adds rows and the admin log stays read-only.

Dropped with reason: the staff-only door is gone, so «a customer is 403», «staff without the fiscal
permission is 403» and the GET history (2: the admin's changelist reads it, searchable by number) do not
apply; the four API-key cases (``vat:read``/``vat:check`` scopes) are lot L3-A's keys; «a UK number is
asked to HMRC» became «a UK number is not VIES's» (the HMRC client is not ported: open point of L2-B).
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages import constants
from django.db import DatabaseError
from django.test import Client, RequestFactory
from django.utils import timezone
from live.models import OutboxEvent

from billing.models import VatCheck
from billing.tests.vies_double import (
    MEMBER_STATE_DOWN,
    VALID,
    no_network,
    vies_answers,
    vies_is_down,
    vies_says,
)

pytestmark = pytest.mark.django_db

HOST = "localhost:8001"
URL = "/api/billing/vat-check"
VAT = "DE812871812"


@pytest.fixture(autouse=True)
def _issuer(issuer_identity):
    return issuer_identity


@pytest.fixture
def signed_in(buyer):
    client = Client()
    client.force_login(buyer)
    return client


@pytest.fixture
def rate_limited(settings):
    """These tests are about the limit: one query a minute."""
    settings.RATELIMIT_ENABLE = True
    settings.VAT_CHECK_RATE = "1/m"


def _ask(client, **payload):
    return client.post(URL, payload, content_type="application/json", HTTP_HOST=HOST)


class TestAsking:
    def test_a_confirmed_number_adds_a_verified_row_and_keeps_the_previous_one(
        self, signed_in
    ):
        earlier = VatCheck.objects.create(vat_number=VAT, status=VatCheck.UNAVAILABLE)

        with vies_answers(
            VALID, requestIdentifier="WAPIAAAAX1", name="ACME GMBH", address="Berlin"
        ) as vies:
            response = _ask(signed_in, vat_number=" de 812-871.812 ", country="DE")

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["vat_number"] == VAT
        assert body["status"] == "verified"
        assert body["valid"] is True
        assert (body["name"], body["address"]) == ("ACME GMBH", "Berlin")
        assert body["consultation_number"] == "WAPIAAAAX1"
        assert body["is_current"] is True
        assert body["reverse_charge"] is True
        assert body["manual_override"] is False
        assert body["checked_at"]
        assert vies.call_count == 1
        # A new row, never an UPDATE: the history is the proof.
        assert VatCheck.objects.filter(vat_number=VAT).count() == 2
        earlier.refresh_from_db()
        assert earlier.status == VatCheck.UNAVAILABLE

    def test_a_current_proof_is_answered_without_asking_again(self, signed_in):
        VatCheck.objects.create(
            vat_number=VAT,
            status=VatCheck.VERIFIED,
            consultation_number="WAPIAAAAXon_file",
        )

        with no_network() as vies:
            response = _ask(signed_in, vat_number=VAT)

        vies.assert_not_called()
        assert (response.json()["status"], response.json()["consultation_number"]) == (
            "verified",
            "WAPIAAAAXon_file",
        )

    def test_a_number_without_its_prefix_is_read_in_the_country_given(self, signed_in):
        with vies_says(**VALID) as vies:
            response = _ask(signed_in, vat_number="812871812", country="de")

        assert response.json()["vat_number"] == VAT
        assert vies.call_args.kwargs["json"]["countryCode"] == "DE"

    def test_vies_down_is_an_answer_not_a_server_error(self, signed_in):
        earlier = VatCheck.objects.create(
            vat_number=VAT, status=VatCheck.VERIFIED, consultation_number="OLD1"
        )
        VatCheck.objects.filter(pk=earlier.pk).update(
            requested_at=timezone.now() - timedelta(days=40)
        )

        with vies_says(**MEMBER_STATE_DOWN):
            response = _ask(signed_in, vat_number=VAT)

        assert response.status_code == 200, response.content
        assert (response.json()["status"], response.json()["valid"]) == (
            "unavailable",
            None,
        )
        assert response.json()["reverse_charge"] is False
        earlier.refresh_from_db()
        assert (earlier.status, earlier.consultation_number) == (
            VatCheck.VERIFIED,
            "OLD1",
        )

    def test_the_network_failing_is_also_a_200_unavailable(self, signed_in):
        with vies_is_down():
            response = _ask(signed_in, vat_number=VAT)

        assert response.status_code == 200
        assert response.json()["status"] == "unavailable"

    def test_a_number_not_in_vies_is_not_valid(self, signed_in):
        with vies_says(
            valid=False, userError="INVALID", requestIdentifier="WAPIAAAAXno"
        ):
            body = _ask(signed_in, vat_number=VAT).json()

        assert (body["status"], body["valid"], body["reverse_charge"]) == (
            "invalid",
            False,
            False,
        )

    def test_a_yes_without_consultation_number_is_still_not_proof(self, signed_in):
        """The hole closed when reading the answer cannot be reopened by a new door."""
        with vies_answers(VALID, requestIdentifier=""):
            body = _ask(signed_in, vat_number=VAT).json()

        assert body["status"] == "unavailable"
        assert body["reverse_charge"] is False

    def test_a_uk_number_is_not_vies_material(self, signed_in):
        with no_network() as vies:
            response = _ask(signed_in, vat_number="GB123456789")

        vies.assert_not_called()
        assert response.status_code == 200
        assert (response.json()["status"], response.json()["valid"]) == (
            "outside_vies",
            None,
        )
        assert VatCheck.objects.count() == 0

    def test_a_spanish_number_has_nothing_to_prove(self, signed_in):
        """A domestic sale is never reverse charge: VIES is not asked (contract §10.6)."""
        with no_network() as vies:
            response = _ask(signed_in, vat_number="B27593136", country="ES")

        vies.assert_not_called()
        assert (response.json()["vat_number"], response.json()["status"]) == (
            "B27593136",
            "national",
        )
        assert response.json()["reverse_charge"] is False

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"vat_number": "  "},
            {"vat_number": "812871812"},
            {"vat_number": "ZZ12345678"},
        ],
        ids=["missing", "blank", "no prefix nor country", "unknown prefix"],
    )
    def test_nothing_to_ask_is_refused_before_spending_a_query(
        self, signed_in, payload
    ):
        with no_network() as vies:
            response = _ask(signed_in, **payload)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_payload"
        assert "vat_number" in response.json()["error"]["fields"]
        vies.assert_not_called()
        assert VatCheck.objects.count() == 0

    def test_a_row_that_could_not_be_written_is_not_reported_as_checked(
        self, signed_in
    ):
        with (
            vies_says(**VALID),
            patch.object(VatCheck, "save", side_effect=DatabaseError("db down")),
        ):
            response = _ask(signed_in, vat_number=VAT)

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "billing.vat_check_not_recorded"

    def test_a_logged_query_is_an_event_of_the_account(self, signed_in, buyer):
        with vies_says(**VALID):
            _ask(signed_in, vat_number=VAT)

        event = OutboxEvent.objects.get(name="billing.vat_check.completed")
        assert (event.scope_kind, event.scope_key) == ("user", str(buyer.pk))
        assert event.payload == {"vat_number": VAT, "status": "verified"}

    def test_the_refusal_speaks_the_language_of_the_account(self, signed_in, buyer):
        """On the panel a signed-in account speaks its own language (``User.language``), not the browser's
        (``base.language``)."""
        buyer.language = "es"
        buyer.save(update_fields=["language"])

        response = signed_in.post(
            URL, {"vat_number": "812871812"}, content_type="application/json", HTTP_HOST=HOST, HTTP_ACCEPT_LANGUAGE="en"
        )

        assert response.status_code == 422
        assert response.json()["error"]["fields"]["vat_number"] == (
            "Escribe el NIF-IVA con el prefijo de su país, p. ej. DE123456789."
        )


class TestWhoMayAsk:
    def test_anonymous_is_401(self, client):
        with no_network() as vies:
            response = _ask(client, vat_number=VAT)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
        vies.assert_not_called()

    def test_every_signed_in_account_may_ask(self, signed_in):
        """The forms of the panel ask before paying: no staff permission is needed any more."""
        with vies_says(**VALID):
            assert _ask(signed_in, vat_number=VAT).status_code == 200


class TestTheSharedRateLimit:
    def test_over_the_limit_is_429_and_the_commission_is_not_called(
        self, signed_in, rate_limited
    ):
        with vies_says(**VALID):
            first = _ask(signed_in, vat_number=VAT)
        with no_network() as vies:
            second = _ask(signed_in, vat_number="FR40303265045")

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "billing.vat_check_throttled"
        vies.assert_not_called()

    def test_the_budget_is_per_person(self, signed_in, rate_limited, make_user):
        other = Client()
        other.force_login(make_user("other@example.com"))
        with vies_says(**VALID):
            _ask(signed_in, vat_number=VAT)
            assert _ask(other, vat_number="FR40303265045").status_code == 200

    def test_the_panel_and_the_admin_spend_the_same_budget(self, buyer, rate_limited):
        """Two doors, one counter: otherwise the limit is whatever the doors add up to."""
        from billing import services

        with vies_says(**VALID):
            services.check_vat_number(VAT, spender=buyer)
        browser = Client()
        browser.force_login(buyer)
        with no_network() as vies:
            response = _ask(browser, vat_number="FR40303265045")

        assert response.status_code == 429
        vies.assert_not_called()

    def test_only_a_real_query_spends_the_budget(self, signed_in, rate_limited):
        """A national number, a UK one, a malformed one or a current proof on file ask nobody, so they
        cost nothing (review of L2-A)."""
        VatCheck.objects.create(vat_number=VAT, status=VatCheck.VERIFIED, consultation_number="WAPIAAAAXon_file")
        with no_network():
            assert _ask(signed_in, vat_number="B27593136", country="ES").status_code == 200
            assert _ask(signed_in, vat_number="GB123456789").status_code == 200
            assert _ask(signed_in, vat_number="812871812").status_code == 422
            assert _ask(signed_in, vat_number=VAT, country="DE").status_code == 200

        with vies_says(**VALID) as vies:
            assert _ask(signed_in, vat_number="FR40303265045", country="FR").status_code == 200
        vies.assert_called_once()

    def test_there_is_a_budget_for_everybody_too(self, signed_in, make_user, settings):
        """Each query is under ERPlora's one requester number: many people at 20 a minute each would
        still flood the Commission, so there is a global budget as well."""
        settings.VAT_CHECK_GLOBAL_RATE = "1/m"
        other = Client()
        other.force_login(make_user("other@example.com"))

        with vies_says(**VALID):
            first = _ask(signed_in, vat_number=VAT, country="DE")
        with no_network() as vies:
            second = _ask(other, vat_number="FR40303265045", country="FR")

        assert first.status_code == 200
        assert (second.status_code, second.json()["error"]["code"]) == (429, "billing.vat_check_throttled")
        vies.assert_not_called()

    def test_one_check_at_a_time_per_person(self, signed_in, buyer):
        """A double click or two tabs do not hold two connections waiting on VIES (finding 3)."""
        from django.core.cache import cache

        from billing import services

        cache.add(services.in_flight_key(buyer), 1, timeout=30)
        with no_network() as vies:
            response = _ask(signed_in, vat_number=VAT, country="DE")

        assert (response.status_code, response.json()["error"]["code"]) == (429, "billing.vat_check_in_progress")
        vies.assert_not_called()

    def test_the_lock_is_given_back_whatever_the_answer(self, signed_in, buyer):
        from django.core.cache import cache

        from billing import services

        with vies_is_down():
            _ask(signed_in, vat_number=VAT, country="DE")
        with patch.object(VatCheck, "save", side_effect=DatabaseError("db down")), vies_says(**VALID):
            _ask(signed_in, vat_number=VAT, country="DE")

        assert cache.get(services.in_flight_key(buyer)) is None


class TestTheAnswerSaysWhatTheSaleWillDo:
    """``reverse_charge`` is what the sale will do, by the engine's own rule, not «VIES said yes»
    (review of L2-A, finding 4)."""

    def test_a_verified_number_of_another_member_state_is_reverse_charged(self, signed_in):
        with vies_says(**VALID):
            body = _ask(signed_in, vat_number=VAT, country="DE").json()

        assert (body["status"], body["valid"], body["reverse_charge"]) == ("verified", True, True)

    def test_without_the_roi_registration_a_verified_number_still_pays_vat(self, signed_in):
        from billing import queries

        policy = queries.fiscal_policy()
        policy.intra_eu_reverse_charge = False
        policy.save()

        with vies_says(**VALID):
            body = _ask(signed_in, vat_number=VAT, country="DE").json()

        assert (body["status"], body["valid"], body["reverse_charge"]) == ("verified", True, False)

    def test_a_payer_in_our_own_country_is_never_reverse_charged(self, signed_in):
        with vies_says(**VALID):
            body = _ask(signed_in, vat_number=VAT, country="ES").json()

        assert (body["valid"], body["reverse_charge"]) == (True, False)

    def test_without_the_payers_country_it_is_not_said(self, signed_in):
        with vies_says(**VALID):
            body = _ask(signed_in, vat_number=VAT).json()

        assert (body["valid"], body["reverse_charge"]) == (True, False)


# ---------------------------------------------------------------------------
# The admin: «Check now in VIES» over the selected rows
# ---------------------------------------------------------------------------

ACTION = "recheck_in_vies"
CHANGELIST = "/admin/billing/vatcheck/"


@pytest.fixture
def support(db):
    return get_user_model().objects.create_superuser(
        email="support@erplora.com", password="x"
    )


@pytest.fixture
def admin_client(client, support):
    client.force_login(support)
    return client


def _messages(response) -> list:
    return list(response.context["messages"])


class TestTheAdminAction:
    def _run(self, admin_client, rows):
        return admin_client.post(
            CHANGELIST,
            {"action": ACTION, "_selected_action": [row.pk for row in rows]},
            follow=True,
        )

    def test_three_rows_mean_three_queries_and_three_new_rows(self, admin_client):
        numbers = ["DE812871812", "FR40303265045", "IT00743110157"]
        rows = [
            VatCheck.objects.create(vat_number=number, status=VatCheck.UNAVAILABLE)
            for number in numbers
        ]

        with vies_says(**VALID) as vies:
            response = self._run(admin_client, rows)

        assert response.status_code == 200
        assert vies.call_count == 3
        assert VatCheck.objects.count() == 6
        for number in numbers:
            assert (
                VatCheck.objects.filter(vat_number=number)
                .order_by("-requested_at")
                .first()
                .status
                == VatCheck.VERIFIED
            )
        assert len(_messages(response)) == 3

    def test_it_asks_again_even_over_a_current_proof(self, admin_client):
        """The support lever forces the question; the panel's door reuses a current proof."""
        row = VatCheck.objects.create(
            vat_number=VAT, status=VatCheck.VERIFIED, consultation_number="WAPIAAAAXold"
        )

        with vies_says(**VALID) as vies:
            self._run(admin_client, [row])

        assert vies.call_count == 1
        assert VatCheck.objects.count() == 2

    def test_two_rows_of_the_same_number_are_one_query(self, admin_client):
        rows = [
            VatCheck.objects.create(vat_number=VAT, status=VatCheck.UNAVAILABLE)
            for _ in range(2)
        ]

        with vies_says(**VALID) as vies:
            self._run(admin_client, rows)

        assert vies.call_count == 1
        assert VatCheck.objects.count() == 3

    def test_vies_down_is_said_and_each_number_keeps_a_complete_row(self, admin_client):
        rows = [
            VatCheck.objects.create(vat_number=n, status=VatCheck.UNAVAILABLE)
            for n in ("DE812871812", "FR40303265045")
        ]

        with vies_says(**MEMBER_STATE_DOWN):
            response = self._run(admin_client, rows)

        messages = _messages(response)
        assert len(messages) == 2
        assert all(message.level == constants.WARNING for message in messages)
        assert VatCheck.objects.count() == 4

    def test_the_rate_limit_stops_the_rest_and_says_which_were_not_asked(
        self, admin_client, rate_limited
    ):
        rows = [
            VatCheck.objects.create(vat_number=n, status=VatCheck.UNAVAILABLE)
            for n in ("DE812871812", "FR40303265045")
        ]

        with vies_says(**VALID) as vies:
            response = self._run(admin_client, rows)

        assert vies.call_count == 1
        assert VatCheck.objects.count() == 3
        assert any(
            message.level == constants.ERROR and "FR40303265045" in message.message
            for message in _messages(response)
        )

    def test_a_row_that_could_not_be_written_is_said(self, admin_client):
        row = VatCheck.objects.create(vat_number=VAT, status=VatCheck.UNAVAILABLE)

        with (
            vies_says(**VALID),
            patch.object(VatCheck, "save", side_effect=DatabaseError("db down")),
        ):
            response = self._run(admin_client, [row])

        assert any(message.level == constants.ERROR for message in _messages(response))

    def test_the_action_is_not_offered_without_the_permission_to_add_checks(self):
        from billing.admin import VatCheckAdmin

        viewer = get_user_model().objects.create_user(
            email="viewer@erplora.com", password="x", is_staff=True
        )
        viewer.user_permissions.add(Permission.objects.get(codename="view_vatcheck"))
        viewer = get_user_model().objects.get(pk=viewer.pk)
        request = RequestFactory().get(CHANGELIST)
        request.user = viewer

        assert ACTION not in VatCheckAdmin(VatCheck, AdminSite()).get_actions(request)

    def test_the_action_is_offered_to_whoever_may_add_checks(self, support):
        from billing.admin import VatCheckAdmin

        request = RequestFactory().get(CHANGELIST)
        request.user = support

        assert ACTION in VatCheckAdmin(VatCheck, AdminSite()).get_actions(request)

    def test_the_log_is_still_read_only(self, support):
        """The action adds rows; it cannot have opened editing or deleting on the way."""
        from billing.admin import VatCheckAdmin

        request = RequestFactory().get(CHANGELIST)
        request.user = support
        model_admin = VatCheckAdmin(VatCheck, AdminSite())

        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
        assert "delete_selected" not in model_admin.get_actions(request)


def test_the_action_speaks_spanish():
    """The admin is used in Spanish: the new lever cannot appear as the only English button."""
    from django.utils import translation
    from django.utils.translation import gettext

    with translation.override("es"):
        assert gettext("Check now in VIES") == "Comprobar ahora en VIES"
