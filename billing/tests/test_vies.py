"""The VIES client: what is asked, what is logged and what happens when it fails.

Ported from ERPlora/saas ``apps/dashboard/fiscal/tests/test_vies.py`` (origin/develop, 21 tests). The
business contract —who is invoiced without VAT— is proved end to end in ``test_vies_contract.py``.
Here, the piece: the query identifies the requester, each answer of the Commission becomes the right
verdict and NOTHING that can go wrong (network down, HTTP 500, unintelligible JSON) ends in
``verified``: when in doubt the VAT is charged, which is the recoverable outcome.

Split by where the code lives now: ``billing.vies`` is the HTTP client (no ORM) and
``billing.services.check_vat_number`` asks it as the identified requester and logs the answer as a
``VatCheck``. Added: the endpoint and the timeout come from the settings, a timeout is an answer
(``unavailable``), and a log that cannot be written is never reported as checked.
"""

from unittest.mock import patch

import pytest
import requests
from django.db import DatabaseError

from billing import queries, services, vies
from billing.models import VatCheck
from billing.tests.vies_double import (
    MEMBER_STATE_DOWN,
    NOT_REGISTERED,
    VALID,
    no_network,
    vies_answers,
    vies_is_down,
    vies_says,
)

pytestmark = pytest.mark.django_db

VAT = "DE812871812"


@pytest.fixture(autouse=True)
def _issuer(issuer_identity):
    return issuer_identity


def _check(vat_number=VAT):
    return services.check_vat_number(vat_number)


class TestNormalising:
    def test_spacing_case_and_punctuation_do_not_matter(self):
        assert vies.normalise(" de 812-871.812 ") == "DE812871812"
        assert vies.normalise(None) == ""

    def test_greece_is_written_as_vies_knows_it(self):
        """A Greek number typed with the ISO code is the same number VIES files under ``EL``."""
        assert vies.normalise("gr 094014201") == "EL094014201"
        assert vies.normalise("EL094014201") == "EL094014201"

    def test_the_country_prefix_is_split_off(self):
        assert vies.split_vat_number("DE812871812") == ("DE", "812871812")
        assert vies.split_vat_number("12345678") == ("", "")
        assert vies.split_vat_number("D1") == ("", "")


class TestTheCountryPrefix:
    def test_a_bare_number_is_read_in_the_payers_country(self):
        assert vies.with_country_prefix("812871812", "de", issuer_country="ES") == "DE812871812"
        assert vies.with_country_prefix("094014201", "GR", issuer_country="ES") == "EL094014201"
        assert vies.with_country_prefix("123456789", "GB", issuer_country="ES") == "GB123456789"

    def test_a_prefixed_national_or_unplaceable_number_is_left_as_it_is(self):
        assert vies.with_country_prefix("FR40303265045", "DE", issuer_country="ES") == "FR40303265045"
        assert vies.with_country_prefix("B27593136", "ES", issuer_country="ES") == "B27593136"
        assert vies.with_country_prefix("123456789", "US", issuer_country="ES") == "123456789"
        assert vies.with_country_prefix("123456789", "", issuer_country="ES") == "123456789"


class TestTheQuery:
    def test_it_identifies_the_requester(self, settings):
        """Without ``requesterMemberStateCode``/``requesterNumber`` VIES returns no consultation number,
        and without a consultation number there is no proof."""
        with vies_says(**VALID) as post:
            _check()

        assert post.call_args.args[0] == settings.VIES_ENDPOINT
        assert post.call_args.kwargs["json"] == {
            "countryCode": "DE",
            "vatNumber": "812871812",
            "requesterMemberStateCode": "ES",
            "requesterNumber": "B27593136",
        }
        # (connect, read): a VIES that does not even accept the connection fails in 3 s, not 5.
        assert post.call_args.kwargs["timeout"] == (settings.VIES_CONNECT_TIMEOUT_SECONDS, settings.VIES_TIMEOUT_SECONDS)

    def test_a_number_without_country_prefix_is_not_asked_about(self):
        with no_network() as post:
            check = _check("12345678")

        post.assert_not_called()
        assert check.status == "invalid"

    def test_greece_is_asked_with_its_vies_prefix(self):
        """Greece files VAT under ``EL``, not its ISO code."""
        with vies_says(**VALID) as post:
            _check("EL094014201")

        assert post.call_args.kwargs["json"]["countryCode"] == "EL"


class TestReadingTheAnswer:
    def test_valid_is_verified_with_its_proof(self):
        with vies_answers(
            VALID,
            requestIdentifier="WAPIAAAAX2",
            name="Hetzner",
            address="Industriestr. 25",
        ):
            check = _check()

        assert check.status == "verified"
        assert check.consultation_number == "WAPIAAAAX2"
        assert check.returned_name == "Hetzner"
        assert check.grants_reverse_charge is True

    def test_a_name_the_member_state_does_not_share_is_no_name(self):
        """Germany answers ``---`` for name and address: the form shows nothing rather than dashes."""
        with vies_answers(VALID, name="---", address="---"):
            check = _check()

        assert (check.status, check.returned_name, check.returned_address) == (
            "verified",
            "",
            "",
        )

    def test_the_older_field_name_is_read_too(self):
        """The per-member-state endpoint says ``isValid``; the REST one, ``valid``. A renamed field
        cannot end in invoices at 0 %."""
        with vies_says(isValid=True, requestIdentifier="WAPIAAAAX3"):
            assert _check().status == "verified"

        with vies_says(isValid=False):
            assert _check().status == "invalid"

    def test_valid_without_a_consultation_number_is_NOT_verified(self):
        """A ``valid: true`` without ``requestIdentifier`` proves nothing (contract §3)."""
        with vies_answers(VALID, requestIdentifier=""):
            check = _check()

        assert check.status == "unavailable"
        assert check.grants_reverse_charge is False

    def test_valid_with_no_identifier_field_at_all_is_NOT_verified(self):
        with vies_says(valid=True):
            check = _check()

        assert check.status == "unavailable"
        assert check.grants_reverse_charge is False

    def test_a_verified_row_without_proof_never_invoices_at_zero(self):
        """The only legitimate ``verified`` row without a consultation number is the manual override."""
        assert (
            VatCheck(
                vat_number=VAT, status="verified", consultation_number=""
            ).grants_reverse_charge
            is False
        )
        assert (
            VatCheck(
                vat_number=VAT, status="verified", consultation_number="WAPIAAAAX9"
            ).grants_reverse_charge
            is True
        )

    def test_not_registered_is_invalid(self):
        with vies_says(**NOT_REGISTERED):
            check = _check()

        assert check.status == "invalid"
        assert check.grants_reverse_charge is False

    @pytest.mark.parametrize(
        "user_error",
        [
            "MS_UNAVAILABLE",
            "SERVICE_UNAVAILABLE",
            "TIMEOUT",
            "SERVER_BUSY",
            "MS_MAX_CONCURRENT_REQ",
            "MS_MAX_CONCURRENT_REQ_TIME",
            "GLOBAL_MAX_CONCURRENT_REQ",
            "GLOBAL_MAX_CONCURRENT_REQ_TIME",
            "VAT_BLOCKED",
            "IP_BLOCKED",
            "INVALID_REQUESTER_INFO",
        ],
    )
    def test_a_member_state_that_cannot_answer_is_unavailable(self, user_error):
        """VIES goes down often, and that is not «not yet»: it is «not verified»."""
        with vies_answers(MEMBER_STATE_DOWN, userError=user_error):
            check = _check()

        assert check.status == "unavailable"
        assert check.grants_reverse_charge is False


class TestItFailsClosed:
    @pytest.mark.parametrize(
        "error",
        [
            OSError("boom"),
            requests.ConnectionError("refused"),
            requests.Timeout("slow"),
        ],
        ids=repr,
    )
    def test_the_network_being_down_is_not_a_verification(self, error):
        with vies_is_down(error):
            assert _check().status == "unavailable"

    def test_an_http_error_is_not_a_verification(self):
        with vies_says(status_code=503):
            assert _check().status == "unavailable"

    def test_a_requester_vies_does_not_accept_is_our_error_and_said_as_one(self, caplog):
        """``INVALID_REQUESTER_INFO``: ERPlora's own VAT number is wrong in CompanyConfig. Not the customer's
        fault, and every check fails until it is fixed: an ERROR, not a quiet «unavailable»."""
        with vies_answers(MEMBER_STATE_DOWN, userError="INVALID_REQUESTER_INFO"):
            assert _check().status == "unavailable"

        assert any(r.levelname == "ERROR" and "INVALID_REQUESTER_INFO" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize("body", [[], "valid", None, 1], ids=["list", "string", "null", "number"])
    def test_an_answer_that_is_not_an_object_is_not_a_verification(self, body):
        with no_network() as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = body

            assert _check().status == "unavailable"

    def test_an_unintelligible_answer_is_not_a_verification(self):
        with vies_says(somethingElse=True):
            assert _check().status == "unavailable"

    def test_an_answer_that_is_not_json_is_not_a_verification(self):
        with no_network() as post:
            post.return_value.status_code = 200
            post.return_value.json.side_effect = ValueError("Expecting value")

            assert _check().status == "unavailable"

    def test_without_our_own_vat_number_nothing_is_asked(self, caplog):
        from billing.models import CompanyConfig

        CompanyConfig.objects.all().delete()

        with no_network() as post:
            check = _check()

        post.assert_not_called()
        assert check.status == "unavailable"
        assert any(
            r.levelname == "ERROR" and "[VIES]" in r.getMessage()
            for r in caplog.records
        )

    def test_the_real_endpoint_is_never_reached_by_a_test(self, settings):
        """The suite's own guard (the root conftest): an unfaked call meets a closed port, fast, as ``unavailable``."""
        assert settings.VIES_ENDPOINT.startswith("http://127.0.0.1:9/")

        assert _check().status == "unavailable"


class TestEveryQueryIsLogged:
    def test_each_query_leaves_its_own_row(self):
        """The log is the proof: it is not overwritten, it accumulates."""
        with vies_says(**NOT_REGISTERED):
            _check()
        with vies_says(**VALID):
            _check()

        assert VatCheck.objects.filter(vat_number=VAT).count() == 2
        assert queries.latest_vat_check(VAT).status == "verified"

    def test_a_failed_query_is_logged_too(self):
        with vies_is_down():
            _check()

        assert queries.latest_vat_check(VAT).status == "unavailable"

    def test_a_row_that_cannot_be_written_is_never_reported_as_checked(self):
        """An answer we cannot keep proves nothing: the caller learns it, it is not a quiet «verified»."""
        with (
            vies_says(**VALID),
            patch.object(VatCheck, "save", side_effect=DatabaseError("db down")),
        ):
            with pytest.raises(services.VatCheckNotRecorded):
                _check()


class TestTheDoor:
    def test_nothing_to_verify(self):
        with no_network() as post:
            assert services.verify_customer_vat("") is None

        post.assert_not_called()

    def test_a_current_verdict_is_reused(self):
        with vies_answers(VALID, requestIdentifier="WAPIAAAAX5"):
            services.verify_customer_vat(VAT)

        with no_network() as post:
            again = services.verify_customer_vat(VAT)

        post.assert_not_called()
        assert again.consultation_number == "WAPIAAAAX5"

    def test_a_verdict_that_could_not_be_had_is_asked_again(self):
        """There is no queue to revalidate in the background (no ``django.tasks``, round 11): the next
        need asks the Commission again, so an ``unavailable`` does not stick for thirty days."""
        with vies_is_down():
            first = services.verify_customer_vat(VAT)
        with vies_says(**VALID) as post:
            second = services.verify_customer_vat(VAT)

        assert (first.status, second.status) == ("unavailable", "verified")
        post.assert_called_once()

    def test_a_uk_number_is_hmrcs_not_vies(self):
        """VIES answers INVALID_INPUT to a GB prefix since Brexit (saas#2205): nothing is asked."""
        with no_network() as post:
            assert services.verify_customer_vat("GB123456789") is None
            assert services.verify_customer_vat("XI123456789") is None

        post.assert_not_called()


class TestTheSettings:
    def test_the_commission_and_a_short_timeout_by_default(self):
        """Read from the environment (``VIES_ENDPOINT``, ``VIES_TIMEOUT_SECONDS``), with safe defaults:
        the REST endpoint that accepts the requester fields, and 5 s, because the query happens while a
        person waits (the form, the checkout)."""
        import config.settings as project_settings

        assert (
            project_settings.VIES_ENDPOINT
            == "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
        )
        assert project_settings.VIES_TIMEOUT_SECONDS == 5.0
        assert project_settings.VIES_CONNECT_TIMEOUT_SECONDS == 3.0
        assert project_settings.VAT_CHECK_RATE == "20/m"
        assert project_settings.VAT_CHECK_GLOBAL_RATE == "60/m"


class TestAtMostThreeQueriesAtOnce:
    """A VIES query holds a database connection while it waits (it runs inside the operation's
    transaction): a process asks at most three at once, and a fourth is ``unavailable`` at once rather
    than queueing (review of L2-A, finding 3)."""

    def test_a_query_beyond_the_three_in_flight_does_not_wait(self):
        for _ in range(3):
            assert vies.VIES_SLOTS.acquire(blocking=False)
        try:
            with no_network() as post:
                answer = vies.ask(VAT, requester=("ES", "B27593136"))
        finally:
            for _ in range(3):
                vies.VIES_SLOTS.release()

        post.assert_not_called()
        assert answer.status == "unavailable"

    def test_the_slot_is_given_back_whatever_the_answer(self):
        with vies_is_down():
            vies.ask(VAT, requester=("ES", "B27593136"))
        with vies_says(**VALID):
            vies.ask(VAT, requester=("ES", "B27593136"))

        taken = [vies.VIES_SLOTS.acquire(blocking=False) for _ in range(3)]
        for _ in range(sum(taken)):
            vies.VIES_SLOTS.release()
        assert taken == [True, True, True]
