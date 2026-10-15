"""The block ``verifactu`` of a business's snapshot (``PUT /internal/hubs/{id}/state``, PLAN-SAAS §2.2; plan
2026-10-15 «Contrato», agreed with the Hub's session):

    "verifactu": {"representation": {"status", "updated_at", "reason"}, "live_paid": bool}

``representation`` is the authorisation as the staff left it (``none`` without rows); ``live_paid`` whether the
business pays for VeriFactu's live sending (a plan that is not Free, or a live ``verifactu`` module). The two
facts are independent: the Hub opens «live» through ERPlora only with both. It travels with the snapshot's
``version``; never a document nor a name.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from fiscal import queries, services
from fiscal.schemas import RepresentationSubmitIn, ReviewIn, WithdrawIn
from fiscal.tests.conftest import make_grant, pdf_b64, staff_ctx, submission
from hubs import queries as hub_queries
from hubs import services as hub_services
from hubs.models import Hub, Subscription, SubscriptionItem
from hubs.schemas import SubscriptionApplyIn

pytestmark = pytest.mark.django_db


def block(hub):
    return hub_queries.hub_snapshot(hub.id)["verifactu"]


def version_of(hub):
    return Hub.objects.get(pk=hub.pk).state_version


def on_free(hub):
    """The business after its Starter trial: the Free plan."""
    Subscription.objects.filter(hub=hub).update(
        trial_end=timezone.now() - timedelta(seconds=1)
    )
    return hub


# --- What the representation says -----------------------------------------------------------------


class TestTheRepresentation:
    def test_a_business_that_never_sent_one_says_none(self, business):
        assert queries.snapshot_block(business.id) == {
            "representation": {"status": "none", "updated_at": None, "reason": ""}
        }

    def test_one_under_review(self, business):
        grant = make_grant(business)

        assert queries.snapshot_block(business.id)["representation"] == {
            "status": "submitted",
            "updated_at": grant.submitted_at.isoformat(),
            "reason": "",
        }

    def test_an_approved_one_says_when_it_was_approved(self, business):
        reviewed = timezone.now() - timedelta(hours=1)
        make_grant(
            business,
            status="approved",
            submitted_at=reviewed - timedelta(days=1),
            reviewed_at=reviewed,
            reason="",
        )

        assert queries.snapshot_block(business.id)["representation"] == {
            "status": "approved",
            "updated_at": reviewed.isoformat(),
            "reason": "",
        }

    def test_a_returned_one_carries_the_reviewers_note(self, business):
        make_grant(
            business,
            status="returned",
            reviewed_at=timezone.now(),
            reason="The DNI copy is unreadable.",
        )

        representation = queries.snapshot_block(business.id)["representation"]

        assert (representation["status"], representation["reason"]) == (
            "returned",
            "The DNI copy is unreadable.",
        )

    def test_a_withdrawn_one_says_when_and_why(self, business):
        revoked = timezone.now()
        make_grant(
            business,
            status="revoked",
            submitted_at=revoked - timedelta(days=31),
            reviewed_at=revoked - timedelta(days=30),
            revoked_at=revoked,
            reason="The company changed its administrator.",
        )

        assert queries.snapshot_block(business.id)["representation"] == {
            "status": "revoked",
            "updated_at": revoked.isoformat(),
            "reason": "The company changed its administrator.",
        }

    def test_the_approval_in_force_holds_while_a_newer_upload_waits(self, business):
        """The old product: a customer who signs again keeps filing while the new document waits."""
        reviewed = timezone.now() - timedelta(days=5)
        make_grant(business, version=1, status="approved", reviewed_at=reviewed)
        make_grant(business, version=2, status="submitted")

        assert (
            queries.snapshot_block(business.id)["representation"]["status"]
            == "approved"
        )

    def test_and_holds_when_the_newer_one_is_returned(self, business):
        make_grant(business, version=1, status="approved", reviewed_at=timezone.now())
        make_grant(business, version=2, status="returned", reason="Not signed.")

        assert queries.snapshot_block(business.id)["representation"] == {
            "status": "approved",
            "updated_at": queries.snapshot_block(business.id)["representation"][
                "updated_at"
            ],
            "reason": "",
        }

    def test_a_withdrawal_after_a_newer_one_was_returned_says_withdrawn(self, business):
        """v1 approved, v2 returned, then v1 withdrawn: the latest change is the withdrawal, as the panel shows."""
        now = timezone.now()
        make_grant(
            business,
            version=1,
            status="revoked",
            submitted_at=now - timedelta(days=10),
            reviewed_at=now - timedelta(days=9),
            revoked_at=now,
            reason="The company changed its administrator.",
        )
        make_grant(
            business,
            version=2,
            status="returned",
            submitted_at=now - timedelta(days=5),
            reviewed_at=now - timedelta(days=4),
            reason="Not signed.",
        )

        assert queries.snapshot_block(business.id)["representation"] == {
            "status": "revoked",
            "updated_at": now.isoformat(),
            "reason": "The company changed its administrator.",
        }

    def test_one_waiting_for_review_comes_before_a_later_withdrawal(self, business):
        """v1 approved, v2 sent, then v1 withdrawn: «submitted», as the panel shows (not approved for the Hub)."""
        now = timezone.now()
        make_grant(
            business,
            version=1,
            status="revoked",
            submitted_at=now - timedelta(days=10),
            reviewed_at=now - timedelta(days=9),
            revoked_at=now,
            reason="The company changed its administrator.",
        )
        sent = now - timedelta(days=2)
        make_grant(business, version=2, status="submitted", submitted_at=sent)

        assert queries.snapshot_block(business.id)["representation"] == {
            "status": "submitted",
            "updated_at": sent.isoformat(),
            "reason": "",
        }

    def test_the_code_of_a_replaced_upload_is_never_a_reason(self, business):
        make_grant(
            business, version=1, status="returned", reason="superseded_by_new_upload"
        )

        assert queries.snapshot_block(business.id)["representation"]["reason"] == ""

    def test_a_note_of_an_approval_never_travels(self, business):
        make_grant(
            business,
            status="approved",
            reviewed_at=timezone.now(),
            reason="internal note",
        )

        assert queries.snapshot_block(business.id)["representation"]["reason"] == ""


# --- Who pays for live sending -------------------------------------------------------------------------


class TestLivePaid:
    def test_free_does_not_pay(self, business):
        assert block(on_free(business))["live_paid"] is False

    def test_a_paid_plan_pays(self, business):
        """Starter is not Free."""
        from hubs.models import Plan

        Subscription.objects.filter(hub=business).update(plan=Plan.objects.get(slug="starter"))

        assert hub_queries.hub_snapshot(business.id)["plan"]["slug"] == "starter"
        assert block(business)["live_paid"] is True

    @pytest.mark.usefixtures("signup_trial")  # the dormant trial, on (no plan carries one since 2026-10-15)
    def test_a_trial_of_a_paid_plan_pays_while_it_lasts(self, business):
        """The sign-up trial's plan is the effective one while it lasts, and it is not Free."""
        assert hub_queries.hub_snapshot(business.id)["plan"]["slug"] == "starter"
        assert block(business)["live_paid"] is True

    def test_standard_pays(self, business):
        from hubs.models import Plan

        Subscription.objects.filter(hub=business).update(
            plan=Plan.objects.get(slug="standard"), trial_plan=None, trial_end=None
        )

        assert block(business)["live_paid"] is True

    def test_free_with_the_verifactu_module_pays(self, business):
        on_free(business)
        SubscriptionItem.objects.create(
            subscription=business.subscription, module_slug="verifactu"
        )

        assert block(business)["live_paid"] is True

    def test_a_verifactu_module_that_ended_does_not(self, business):
        on_free(business)
        SubscriptionItem.objects.create(
            subscription=business.subscription,
            module_slug="verifactu",
            valid_until=timezone.now() - timedelta(minutes=1),
        )

        assert block(business)["live_paid"] is False

    def test_another_module_does_not(self, business):
        on_free(business)
        SubscriptionItem.objects.create(
            subscription=business.subscription, module_slug="inventory"
        )

        assert block(business)["live_paid"] is False

    def test_approved_on_free_is_approved_and_unpaid(self, business):
        """Two independent facts: the documentation is validated, the live sending is not paid."""
        on_free(business)
        make_grant(business, status="approved", reviewed_at=timezone.now())

        assert (
            block(business)["representation"]["status"],
            block(business)["live_paid"],
        ) == ("approved", False)


# --- (a) Two businesses, each its own ----------------------------------------------------------------------


def test_two_businesses_each_carry_their_own_state(business, other_business, reviewer):
    approved = make_grant(business, status="approved", reviewed_at=timezone.now())
    services.representation_submit(
        hub_services.system_ctx_for(other_business.id),
        RepresentationSubmitIn(hub_id=other_business.id, **submission()),
    )

    assert block(business)["representation"]["status"] == "approved"
    assert block(other_business)["representation"]["status"] == "submitted"
    assert approved.hub_id == business.id


def test_what_happens_in_one_business_never_bumps_another(
    business, other_business, reviewer
):
    make_grant(business, status="approved", reviewed_at=timezone.now())
    before = version_of(business)

    services.representation_submit(
        hub_services.system_ctx_for(other_business.id),
        RepresentationSubmitIn(hub_id=other_business.id, **submission()),
    )
    waiting = make_grant(other_business, version=2, status="submitted")
    services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))

    assert version_of(business) == before
    assert block(business)["representation"]["status"] == "approved"
    assert block(other_business)["representation"]["status"] == "approved"


# --- (b) A withdrawal reaches the Hub with a newer version --------------------------------------------


def test_a_withdrawal_reaches_the_hub_after_the_commit(
    business, reviewer, hub_double, django_capture_on_commit_callbacks
):
    hub_services.sync_hub(business.id)
    approved = make_grant(business, status="approved", reviewed_at=timezone.now())
    before = version_of(business)

    with django_capture_on_commit_callbacks(execute=True):
        services.representation_withdraw(
            staff_ctx(reviewer),
            WithdrawIn(id=approved.id, reason="Revoked by the AEAT."),
        )

    state = hub_double.calls_to("PUT", f"/internal/hubs/{business.id}/state")[-1].body
    assert state["version"] == before + 1 == hub_double.versions[str(business.id)]
    assert state["verifactu"]["representation"]["status"] == "revoked"
    assert state["verifactu"]["representation"]["reason"] == "Revoked by the AEAT."
    assert Hub.objects.get(pk=business.pk).pushed_state_version == before + 1


# --- (c) Losing the payment and keeping the validation ----------------------------------------------------


def test_a_module_that_stops_being_live_leaves_modules_and_keeps_the_approval(business):
    on_free(business)
    make_grant(business, status="approved", reviewed_at=timezone.now())
    item = SubscriptionItem.objects.create(
        subscription=business.subscription, module_slug="verifactu"
    )
    assert "verifactu" in [
        module["id"] for module in hub_queries.hub_snapshot(business.id)["modules"]
    ]

    SubscriptionItem.objects.filter(pk=item.pk).update(
        valid_until=timezone.now() - timedelta(seconds=1)
    )

    snapshot = hub_queries.hub_snapshot(business.id)
    assert "verifactu" not in [module["id"] for module in snapshot["modules"]]
    assert (
        snapshot["verifactu"]["representation"]["status"],
        snapshot["verifactu"]["live_paid"],
    ) == (
        "approved",
        False,
    )


def test_dropping_to_free_loses_live_paid_with_a_newer_version_and_keeps_the_approval(
    business, hub_double, django_capture_on_commit_callbacks
):
    """What Stripe says (``hubs.subscription.apply``) changes the plan the Hub sees, so the snapshot is bumped
    and pushed: ``live_paid`` turns false; the approval stays."""
    Subscription.objects.filter(hub=business).update(trial_plan=None, trial_end=None)
    hub_services.subscription_apply(
        hub_services.system_ctx_for(business.id),
        SubscriptionApplyIn(hub_id=business.id, plan="starter"),
    )
    make_grant(business, status="approved", reviewed_at=timezone.now())
    assert block(business)["live_paid"] is True
    before = version_of(business)

    with django_capture_on_commit_callbacks(execute=True):
        hub_services.subscription_apply(
            hub_services.system_ctx_for(business.id),
            SubscriptionApplyIn(hub_id=business.id, plan="free"),
        )

    assert version_of(business) == before + 1
    state = hub_double.calls_to("PUT", f"/internal/hubs/{business.id}/state")[-1].body
    assert (state["version"], state["plan"]["slug"]) == (before + 1, "free")
    assert state["verifactu"] == {
        "representation": state["verifactu"]["representation"],
        "live_paid": False,
    }
    assert state["verifactu"]["representation"]["status"] == "approved"


# --- (d) What stays owed is pushed again by the reconciliation ------------------------------------------


def test_reconcile_pushes_an_owed_state_with_its_block(
    business, reviewer, offline_hub, settings
):
    from hubs.tests.conftest import SECRET
    from hubs.tests.hub_double import HubDouble

    waiting = make_grant(business, status="submitted")
    services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))
    owed = Hub.objects.get(pk=business.pk)
    assert owed.pushed_state_version < owed.state_version

    double = HubDouble(SECRET).start()
    try:
        settings.INTERNAL_SHARED_SECRET = SECRET
        settings.HUB_INTERNAL_URL = double.url
        hub_services.reconcile()
    finally:
        double.stop()

    state = double.calls_to("PUT", f"/internal/hubs/{business.id}/state")[-1].body
    assert state["version"] == owed.state_version
    assert state["verifactu"]["representation"]["status"] == "approved"
    assert Hub.objects.get(pk=business.pk).pushed_state_version == owed.state_version


# --- (e) No document ever leaves --------------------------------------------------------------------------


def test_the_hub_never_receives_a_document(
    business, reviewer, hub_double, django_capture_on_commit_callbacks
):
    documents = {
        "signed_model": pdf_b64("the-signed-model-marker"),
        "id_copy": pdf_b64("the-id-copy-marker"),
    }
    with django_capture_on_commit_callbacks(execute=True):
        services.representation_submit(
            hub_services.system_ctx_for(business.id),
            RepresentationSubmitIn(
                hub_id=business.id, **submission(documents=documents)
            ),
        )
    with django_capture_on_commit_callbacks(execute=True):
        waiting = make_grant(business, version=2)
        services.representation_approve(staff_ctx(reviewer), ReviewIn(id=waiting.id))

    sent = b"".join(call.raw for call in hub_double.calls)
    assert sent
    for value in documents.values():
        assert value.encode() not in sent
    for forbidden in (
        b"%PDF",
        b"JVBER",
        b"marker",
        b"signed_model",
        b"id_copy",
        # The taxpayer and the signer (``Manolo García``; the business itself is «Bar Manolo»).
        b"Garc",
        b"12345678Z",
    ):
        assert forbidden not in sent


# --- The snapshot's shape ---------------------------------------------------------------------------------


def test_the_snapshot_names_the_business_by_its_address(business):
    snapshot = hub_queries.hub_snapshot(business.id)

    assert (snapshot["hub_id"], snapshot["slug"]) == (str(business.id), "bar-manolo")
    assert set(snapshot["verifactu"]) == {"representation", "live_paid"}
