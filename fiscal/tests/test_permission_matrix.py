"""Who may do what with a business's signed authorisation, by role (plan 2026-10-15; round 17 §2.7 for the
roles): the owner and the administrators read its state on the business's page; a manager or an employee
does not; somebody without access (a stranger, or an invitation not answered yet) does not learn the business
exists. Every other operation of fiscal belongs to the platform (the Hub's upload, the tell) or to the staff
(the review in the admin): no role of a business runs them, whatever its rank.

One table for every operation of fiscal, so a new operation cannot slip in without its row. Same reading as
``hubs/tests/test_permission_matrix.py``.
"""

import pytest
from live.errors import NotFound, OperationError, PermissionDenied

from fiscal import queries, services
from fiscal.schemas import (
    NotifyIn,
    RepresentationStatusIn,
    RepresentationSubmitIn,
    ReturnIn,
    ReviewIn,
    StampDeleteIn,
    StampUploadIn,
    WithdrawIn,
)
from fiscal.tests.conftest import make_grant, submission
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db

OK, DENIED, HIDDEN = "ok", 403, 404
ROLES = ["owner", "admin", "manager", "employee", "invitee", "stranger"]


def call(name, hub):
    grant = make_grant(hub)
    return {
        "representation.status": (queries.representation_status, RepresentationStatusIn(id=hub.id)),
        "representation.submit": (
            services.representation_submit,
            RepresentationSubmitIn(hub_id=hub.id, **submission()),
        ),
        "representation.approve": (services.representation_approve, ReviewIn(id=grant.id)),
        "representation.return": (services.representation_return, ReturnIn(id=grant.id, reason="Blurry.")),
        "representation.withdraw": (services.representation_withdraw, WithdrawIn(id=grant.id, reason="Gone.")),
        "representation.notify": (services.representation_notify, NotifyIn(id=hub.id)),
        "stamp.upload": (services.stamp_upload, StampUploadIn(png_base64="")),
        "stamp.delete": (services.stamp_delete, StampDeleteIn()),
    }[name]


MATRIX = {
    #                           owner admin   manager employee invitee stranger
    "representation.status": (OK, OK, DENIED, DENIED, HIDDEN, HIDDEN),
    # The platform's and the staff's: no account runs them (``fiscal.manage`` is no role's).
    "representation.submit": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
    "representation.approve": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
    "representation.return": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
    "representation.withdraw": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
    "representation.notify": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
    # ERPlora's stamp (FISCAL-F06): the staff's alone.
    "stamp.upload": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
    "stamp.delete": (DENIED, DENIED, DENIED, DENIED, DENIED, DENIED),
}


def outcome(operation, ctx, data):
    try:
        operation(ctx, data)
    except PermissionDenied:
        return DENIED
    except NotFound:
        return HIDDEN
    except OperationError:
        return OK  # past the role: refused by the domain (409, 422)
    return OK


@pytest.mark.parametrize("name", MATRIX)
@pytest.mark.parametrize("role", ROLES)
def test_the_role_decides(business, team, name, role):
    operation, data = call(name, business)

    assert outcome(operation, ctx_for(team[role]), data) == MATRIX[name][ROLES.index(role)]


def test_every_operation_of_fiscal_has_its_row():
    from live.operations import registry

    assert {name for name in registry if name.startswith("fiscal.")} == {f"fiscal.{name}" for name in MATRIX}
