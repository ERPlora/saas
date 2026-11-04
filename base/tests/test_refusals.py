"""The notice on top of a form whose fields a service refused (saas#265): it points at the fields, each of which
keeps its own message. The same words as ``live.ninja``'s refusal of the schema, so a person never reads two."""

import pytest
from django.utils import translation
from live.errors import InvalidPayload

from base.refusals import fields_refused
from base.tests.test_locale import messages_of


class TestAFieldRefusal:
    def test_it_is_the_invalid_payload_of_the_contract_with_the_fields_kept(self):
        refusal = fields_refused({"vat_number": "Enter a VAT number."})

        assert isinstance(refusal, InvalidPayload)
        assert (refusal.status, refusal.code) == (422, "invalid_payload")
        assert refusal.fields == {"vat_number": "Enter a VAT number."}

    def test_it_can_carry_a_code_of_its_own(self):
        assert fields_refused({"reason": "Write it."}, code="fiscal.reason_required").code == "fiscal.reason_required"

    @pytest.mark.parametrize(
        "language, notice",
        [("en", "Check the highlighted details."), ("es", "Revisa los datos marcados.")],
    )
    def test_its_notice_points_at_the_fields_in_the_language_in_force(self, language, notice):
        with translation.override(language):
            assert fields_refused({"name": "No."}).message == notice


@pytest.mark.parametrize("app", ["accounts", "billing", "hubs", "fiscal"])
def test_no_app_words_a_refusal_with_the_sentence_nobody_understood(app):
    assert "Invalid payload" not in {message for _, message in messages_of(app)}
