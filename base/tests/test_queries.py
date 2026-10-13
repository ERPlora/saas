"""base.session.me: who is in front of the SaaS SPA, in the shape the shell reads.

The SaaS has no apps menu yet (the panel arrives with its pages): ``menu`` and ``apps`` are empty
and no permission is granted. An anonymous visitor gets ``user: None``, which tells the shell's
auth gate to send it to the login.
"""

import pytest
from live.context import OperationContext, Scope
from live.operations import get

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


def test_a_signed_in_user_is_labelled_with_its_full_name(ana):
    me = session_me(ana, Scope("user", str(ana.pk)))

    assert me["user"] == {"id": str(ana.pk), "label": "Ana García"}
    assert me["scope"] == {"kind": "user", "key": str(ana.pk)}
    assert (me["permissions"], me["menu"], me["apps"]) == ([], [], [])


def test_without_a_name_the_label_is_the_email(django_user_model):
    user = django_user_model.objects.create_user(email="bo@example.com", password="x")

    assert (
        session_me(user, Scope("user", str(user.pk)))["user"]["label"]
        == "bo@example.com"
    )
