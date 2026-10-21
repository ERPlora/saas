"""The inputs of whatsapp's operations refuse what the operation would not know what to do with."""

import pytest
from pydantic import ValidationError

from whatsapp.schemas import ClaimIn, RecordIn


def test_a_claim_takes_between_one_and_five_hundred():
    assert ClaimIn().limit == 50
    for limit in (0, 501):
        with pytest.raises(ValidationError):
            ClaimIn(limit=limit)


def test_a_push_ends_in_one_of_four_ways():
    for outcome in ("delivered", "retry", "refused", "drop"):
        RecordIn(id="0199e7c2-0000-7000-8000-000000000001", revision=0, outcome=outcome)
    with pytest.raises(ValidationError):
        RecordIn(id="0199e7c2-0000-7000-8000-000000000001", revision=0, outcome="maybe")
