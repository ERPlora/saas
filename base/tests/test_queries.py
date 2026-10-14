"""base.session.me: who is in front of the SaaS SPA, in the shape the shell reads.

A signed-in account gets the panel's menu of ``base/navigation.py`` (round 17, PLAN-SAAS §3.6
point 1), translated into its language, with the Store marked ``webOnly``; ``apps`` stays empty (the
SaaS has no modules, PLAN §20.3.5). An anonymous visitor gets ``user: None`` and no menu, which tells
the shell's auth gate to send it to the login.
"""

import pytest
from live.context import OperationContext, Scope
from live.operations import get

from base import navigation
from base.schemas import SessionMeIn, SessionMeOut

pytestmark = pytest.mark.django_db


def session_me(actor=None, scope=Scope("user", "anonymous"), language="en"):
    ctx = OperationContext(scope=scope, actor=actor, language=language)
    return get("base.session.me")(ctx, SessionMeIn()).model_dump(mode="json")


def test_declaration():
    op = get("base.session.me")

    assert (op.kind, op.permission, op.input, op.output) == (
        "query",
        None,
        SessionMeIn,
        SessionMeOut,
    )


def test_anonymous():
    assert session_me(language="es") == {
        "user": None,
        "scope": {"kind": "user", "key": "anonymous"},
        "permissions": [],
        "menu": [],
        "apps": [],
        "language": "es",
    }


def test_a_signed_in_user_is_labelled_with_its_full_name_and_carries_its_email(ana):
    me = session_me(ana, Scope("user", str(ana.pk)))

    assert me["user"] == {"id": str(ana.pk), "label": "Ana García", "email": "ana@example.com"}
    assert me["scope"] == {"kind": "user", "key": str(ana.pk)}
    assert (me["permissions"], me["apps"]) == ([], [])


def test_a_signed_in_user_gets_the_panels_menu(ana):
    me = session_me(ana, Scope("user", str(ana.pk)))

    assert me["menu"] == [
        {
            "id": "base",
            "label": "",
            "items": [
                {"path": "/businesses", "label": "Businesses", "icon": "lucide:store", "webOnly": False},
                {"path": "/store", "label": "Store", "icon": "lucide:shopping-bag", "webOnly": True},
                {"path": "/billing", "label": "Billing", "icon": "lucide:receipt", "webOnly": False},
                {"path": "/account", "label": "Account", "icon": "lucide:circle-user", "webOnly": False},
            ],
        }
    ]


def test_the_menu_is_translated_into_the_contexts_language(ana):
    """A live re-run happens outside the request that activated the language: the query sets it."""
    me = session_me(ana, Scope("user", str(ana.pk)), language="es")

    [section] = me["menu"]
    assert [item["label"] for item in section["items"]] == ["Negocios", "Tienda", "Facturación", "Cuenta"]


def test_the_menu_is_the_one_of_base_navigation(ana):
    me = session_me(ana, Scope("user", str(ana.pk)))

    [section] = me["menu"]
    assert [item["path"] for item in section["items"]] == [nav.path for nav in navigation.NAVIGATION]
    assert [item["path"] for item in section["items"] if item["webOnly"]] == ["/store"]


def test_without_a_name_the_label_is_the_email(django_user_model):
    user = django_user_model.objects.create_user(email="bo@example.com", password="x")

    assert (
        session_me(user, Scope("user", str(user.pk)))["user"]["label"]
        == "bo@example.com"
    )
