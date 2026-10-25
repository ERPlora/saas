"""The panel's menu (round 17, PLAN-SAAS §3.6 point 1): Businesses · Store · Billing · Account.

The SaaS's apps are platform apps, which declare no ``navigation`` (``live.checks``, PLAN §20.3.3),
so the menu is declared once in ``base/navigation.py`` and ``base.session.me`` sends it, already
translated. The Store sells, so it is the only entry the app surfaces leave out (``webOnly``,
PLAN-SAAS §3.6 point 6).
"""

import pytest
from django.utils import translation
from live.meta import Nav

from base import navigation


def test_four_entries_in_the_mockups_order_with_their_icons():
    assert [(nav.id, nav.path, nav.icon) for nav in navigation.NAVIGATION] == [
        ("businesses", "/dashboard/businesses", "lucide:store"),
        ("store", "/dashboard/store", "lucide:shopping-bag"),
        ("billing", "/dashboard/billing", "lucide:receipt"),
        ("account", "/dashboard/account", "lucide:circle-user"),
    ]
    assert all(isinstance(nav, Nav) for nav in navigation.NAVIGATION)


def test_only_the_store_is_web_only():
    assert navigation.WEB_ONLY == frozenset({"store"})
    assert navigation.WEB_ONLY <= {nav.id for nav in navigation.NAVIGATION}


@pytest.mark.parametrize(
    ("language", "labels"),
    [
        ("en", ["Businesses", "Store", "Billing", "Account"]),
        ("es", ["Negocios", "Tienda", "Facturación", "Cuenta"]),
    ],
)
def test_labels_are_translated_when_read(language, labels):
    with translation.override(language):
        assert [str(nav.label) for nav in navigation.NAVIGATION] == labels


def test_the_menu_is_one_section_without_a_header():
    """An empty label paints no divider header (packages/ui ``SessionMenuSection``)."""
    with translation.override("en"):
        assert navigation.menu() == [
            {
                "id": "base",
                "label": "",
                "items": [
                    {
                        "path": "/dashboard/businesses",
                        "label": "Businesses",
                        "icon": "lucide:store",
                        "webOnly": False,
                    },
                    {
                        "path": "/dashboard/store",
                        "label": "Store",
                        "icon": "lucide:shopping-bag",
                        "webOnly": True,
                    },
                    {
                        "path": "/dashboard/billing",
                        "label": "Billing",
                        "icon": "lucide:receipt",
                        "webOnly": False,
                    },
                    {
                        "path": "/dashboard/account",
                        "label": "Account",
                        "icon": "lucide:circle-user",
                        "webOnly": False,
                    },
                ],
            }
        ]


def test_the_menu_is_in_the_active_language_as_plain_strings():
    with translation.override("es"):
        [section] = navigation.menu()

    assert [item["label"] for item in section["items"]] == [
        "Negocios",
        "Tienda",
        "Facturación",
        "Cuenta",
    ]
    assert all(type(item["label"]) is str for item in section["items"])
