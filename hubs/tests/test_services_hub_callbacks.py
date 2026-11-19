"""The Hub's callback that a business is ready, ``hubs.business.mark_ready``: only the system marks it, once,
and the owner is mailed after the COMMIT."""

import pytest
from live.errors import PermissionDenied

from hubs import services
from hubs.models import Hub
from hubs.schemas.hub_callbacks import MarkReadyIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


# --- Ready ----------------------------------------------------------------------------------------


class TestMarkReady:
    def system(self, hub):
        return services.hub_callbacks.system_ctx_for(hub.id)

    def test_the_hubs_callback_makes_it_active(self, business):
        ready = services.hub_callbacks.business_mark_ready(
            self.system(business), MarkReadyIn(id=business.id)
        )
        business.refresh_from_db()

        assert (business.status, ready.status) == ("active", "active")
        assert business.ready_at is not None

    def test_it_is_idempotent(self, business):
        services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))
        first = Hub.objects.get(pk=business.pk).ready_at

        services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert Hub.objects.get(pk=business.pk).ready_at == first

    def test_a_deleted_business_stays_deleted(self, business, owner):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert Hub.objects.get(pk=business.pk).status == "deleting"

    def test_a_suspended_business_keeps_its_status(self, business):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.SUSPENDED)

        services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert Hub.objects.get(pk=business.pk).status == "suspended"

    def test_only_the_system_marks_a_business_ready(self, business, owner):
        with pytest.raises(PermissionDenied):
            services.hub_callbacks.business_mark_ready(ctx_for(owner), MarkReadyIn(id=business.id))

    def test_the_owner_is_mailed_once_after_the_commit(
        self, business, owner, mailoutbox, django_capture_on_commit_callbacks
    ):
        """HUBS-F04/HUBS-F07: «your business is ready», only once,
        and never inside the transaction that marks it ready."""
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))
        assert mailoutbox == []
        for callback in callbacks:
            callback()
        with django_capture_on_commit_callbacks(execute=True):
            services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert [message.to for message in mailoutbox] == [[owner.email]]

    def test_a_business_that_does_not_open_is_not_announced(
        self, business, mailoutbox, django_capture_on_commit_callbacks
    ):
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING)

        with django_capture_on_commit_callbacks(execute=True):
            services.hub_callbacks.business_mark_ready(self.system(business), MarkReadyIn(id=business.id))

        assert mailoutbox == []

    def test_the_system_acts_in_the_owners_channel(self, business, owner):
        """Its event reaches the owner's live lists (the scope is the user)."""
        assert self.system(business).scope.key == str(owner.pk)
