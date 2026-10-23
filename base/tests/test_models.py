"""ACCOUNTS-G64: ``SiteSettings``, the one row of the site's switches (maintenance mode and its message)."""

import pytest
from django.db import IntegrityError, transaction

from base.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_it_is_born_off_with_no_message():
    site = SiteSettings.objects.create()

    assert site.maintenance_mode is False
    assert site.maintenance_message_en == ""
    assert site.maintenance_message_es == ""


def test_there_is_only_one_row():
    SiteSettings.objects.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        SiteSettings.objects.create()


def test_its_key_is_a_uuid7():
    site = SiteSettings.objects.create()

    assert site.pk.version == 7


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Back at 14:00."), ("es", "Volvemos a las 14:00."), ("de", "Back at 14:00.")],
)
def test_the_message_is_the_one_of_the_language_or_the_english_one(language, expected):
    site = SiteSettings(maintenance_message_en="Back at 14:00.", maintenance_message_es="Volvemos a las 14:00.")

    assert site.message_for(language) == expected


def test_without_a_spanish_message_spanish_gets_the_english_one():
    site = SiteSettings(maintenance_message_en="Back at 14:00.")

    assert site.message_for("es") == "Back at 14:00."


def test_without_any_message_there_is_none():
    assert SiteSettings().message_for("es") == ""
