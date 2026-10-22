"""``{% support_email %}`` (public/templatetags/support.py): the support address for a template rendered without
the context processors, like Django's 500 page (``templates/errors/base.html``). One source: ``SUPPORT_EMAIL``."""

from django.template import Context, Template


def test_it_writes_the_support_address_of_the_settings(settings):
    settings.SUPPORT_EMAIL = "help@erplora.test"

    assert Template("{% load support %}{% support_email %}").render(Context()) == "help@erplora.test"


def test_it_is_escaped_like_any_value(settings):
    settings.SUPPORT_EMAIL = 'a"b@erplora.test'

    assert Template("{% load support %}{% support_email %}").render(Context()) == "a&quot;b@erplora.test"
