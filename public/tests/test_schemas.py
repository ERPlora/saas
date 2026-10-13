"""Schemas of the public web's operations (OpenAPI and the Hub's runtime)."""

import pytest
from pydantic import ValidationError

from public.schemas import AppReleaseIn, AppReleaseOut


def test_the_release_takes_no_input():
    assert AppReleaseIn().model_dump() == {}


@pytest.mark.parametrize("version", ["1.4.0", None])
def test_the_release_is_a_version_or_null(version):
    """The Hub's contract (hub#400): ``{"version": str | null}``, never a number."""
    assert AppReleaseOut(version=version).model_dump() == {"version": version}


def test_the_release_requires_its_key():
    with pytest.raises(ValidationError):
        AppReleaseOut()
