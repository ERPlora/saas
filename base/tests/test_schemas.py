"""Shape of base.session.me, the contract the shell reads (packages/ui src/shell/session.ts)."""

import pydantic
import pytest

from base.schemas import SessionMeIn, SessionMeOut

FULL = {
    "user": {
        "id": "0192f0c4-7a1e-7000-8000-000000000001",
        "label": "Ana García",
        "email": "ana@example.com",
    },
    "scope": {"kind": "user", "key": "0192f0c4-7a1e-7000-8000-000000000001"},
    "permissions": [],
    "menu": [
        {
            "id": "base",
            "label": "",
            "items": [
                {"path": "/businesses", "label": "Negocios", "icon": "lucide:store", "webOnly": False},
                {"path": "/store", "label": "Tienda", "icon": "lucide:shopping-bag", "webOnly": True},
            ],
        }
    ],
    "apps": [],
    "language": "es",
}


def test_input_is_empty():
    assert SessionMeIn.model_fields == {}


def test_full_output_round_trips():
    assert SessionMeOut.model_validate(FULL).model_dump(mode="json") == FULL


def test_anonymous_output():
    assert SessionMeOut.model_validate({**FULL, "user": None}).user is None


@pytest.mark.parametrize(
    "missing", ["user", "scope", "permissions", "menu", "apps", "language"]
)
def test_every_key_the_shell_reads_is_required(missing):
    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate(
            {key: value for key, value in FULL.items() if key != missing}
        )


def test_the_user_carries_its_email():
    """The user menu shows it under the name (packages/ui ``SessionUser.email``)."""
    user = dict(FULL["user"])
    del user["email"]

    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate({**FULL, "user": user})


def test_every_menu_item_says_whether_it_is_web_only():
    """``webOnly``, as the shell reads it (packages/ui ``SessionMenuItem.webOnly``)."""
    [section] = FULL["menu"]
    item = {key: value for key, value in section["items"][0].items() if key != "webOnly"}

    with pytest.raises(pydantic.ValidationError):
        SessionMeOut.model_validate({**FULL, "menu": [{**section, "items": [item]}]})
