"""What each answer of the Commission is read as, the proof it leaves and what the log says about it."""

import pytest

from billing import vies
from billing.tests.vies_double import MEMBER_STATE_DOWN, NOT_REGISTERED, VALID, no_network, vies_answers, vies_says

VAT = "DE812871812"
REQUESTER = ("ES", "B27593136")


def _ask():
    return vies.ask(VAT, requester=REQUESTER)


def _answer(base, **overrides):
    with vies_answers(base, **overrides):
        return _ask()


@pytest.fixture
def said(caplog):
    caplog.set_level("INFO", logger="billing.vies")

    def lines():
        return [(record.levelname, record.getMessage()) for record in caplog.records if record.name == "billing.vies"]

    return lines


class TestVerified:
    def test_the_proof_the_name_and_the_address_are_kept(self, said):
        assert _answer(VALID) == vies.ViesAnswer(
            vies.VERIFIED, "WAPIAAAAXjHIQOZ", "Hetzner Online GmbH", "Industriestr. 25\n91710 Gunzenhausen"
        )
        assert said() == []

    @pytest.mark.parametrize("identifier, number", [("  WAPI1 ", "WAPI1"), (12345, "12345")])
    def test_the_consultation_number_is_read_however_it_comes(self, identifier, number):
        assert _answer(VALID, requestIdentifier=identifier).consultation_number == number

    def test_a_name_longer_than_its_column_is_cut(self):
        assert _answer(VALID, name="N" * 300).name == "N" * 255

    def test_a_name_and_an_address_not_shared_are_none(self):
        answer = _answer(VALID, name="---", address="---")

        assert (answer.status, answer.name, answer.address) == (vies.VERIFIED, "", "")

    @pytest.mark.parametrize("identifier", ["", "   ", None])
    def test_without_a_consultation_number_it_is_no_proof_and_an_error_of_ours(self, identifier, said):
        assert _answer(VALID, requestIdentifier=identifier) == vies.ViesAnswer(vies.UNAVAILABLE)

        [(level, message)] = said()
        assert level == "ERROR"
        assert message.startswith(f"[VIES] {VAT} came back VALID but WITHOUT a consultation number")


class TestNotRegistered:
    def test_it_is_invalid_and_keeps_its_consultation_number(self):
        assert _answer(NOT_REGISTERED) == vies.ViesAnswer(vies.INVALID, "WAPIAAAAXinvalid")

    @pytest.mark.parametrize(
        "user_error, reason",
        [("INVALID_INPUT", "INVALID_INPUT"), ("invalid_input", "INVALID_INPUT"), ("", "INVALID"), (None, "INVALID"), (7, "7")],
    )
    def test_the_log_says_why(self, user_error, reason, said):
        assert _answer(NOT_REGISTERED, userError=user_error).status == vies.INVALID
        assert said() == [("INFO", f"[VIES] {VAT} is NOT registered in VIES ({reason}): VAT is charged")]


class TestCouldNotAnswer:
    @pytest.mark.parametrize("user_error", ["MS_UNAVAILABLE", "ms_unavailable"])
    def test_a_member_state_that_is_down_is_a_warning(self, user_error, said):
        answer = _answer(MEMBER_STATE_DOWN, userError=user_error, requestIdentifier="WAPIdown")

        assert answer == vies.ViesAnswer(vies.UNAVAILABLE, "WAPIdown")
        assert said() == [("WARNING", f"[VIES] {VAT} could not be checked (MS_UNAVAILABLE): VAT is charged")]

    def test_a_requester_vies_refuses_is_an_error_of_ours(self, said):
        answer = _answer(MEMBER_STATE_DOWN, userError="INVALID_REQUESTER_INFO", requestIdentifier="WAPIours")

        assert answer == vies.ViesAnswer(vies.UNAVAILABLE, "WAPIours")
        assert said() == [
            (
                "ERROR",
                f"[VIES] VIES refuses the requester (INVALID_REQUESTER_INFO) asking about {VAT}: ERPlora's own VAT "
                "number in CompanyConfig is wrong, and every check fails until it is fixed. VAT is charged",
            )
        ]

    def test_an_error_rules_over_a_valid_in_the_same_answer(self):
        assert _answer(VALID, userError="TIMEOUT").status == vies.UNAVAILABLE


class TestUnintelligible:
    @pytest.mark.parametrize("valid", ["true", 1, "false", 0, "", None])
    def test_a_valid_that_is_not_a_yes_or_a_no(self, valid, said):
        body = {"valid": valid, "requestIdentifier": "WAPI1"}
        with vies_says(**body):
            assert _ask() == vies.ViesAnswer(vies.UNAVAILABLE)

        assert said() == [("ERROR", f"[VIES] Unintelligible answer about {VAT}: {body!r}")]

    @pytest.mark.parametrize("body", [[], ["valid"], "valid", None, 1, True], ids=repr)
    def test_an_answer_that_is_not_an_object(self, body, said):
        with no_network() as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = body

            assert _ask() == vies.ViesAnswer(vies.UNAVAILABLE)

        assert said() == [("ERROR", f"[VIES] Unintelligible answer about {VAT}: {body!r}")]

    def test_the_two_names_of_the_field_never_contradict_a_no(self):
        with vies_says(valid=False, isValid=True, requestIdentifier="WAPI1"):
            assert _ask().status == vies.INVALID
