"""Opening a business, ``hubs.business.open``: it answers the Hub's start, mints no code and remembers the
business."""

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound

from accounts.models import AuthExchangeCode
from hubs import services
from hubs.models import Hub, HubMember
from hubs.schemas.businesses import BusinessOpenIn
from hubs.tests.conftest import ctx_for

pytestmark = pytest.mark.django_db


# --- Opening --------------------------------------------------------------------------------------


class TestOpen:
    """«Open»: the Hub binds the jump to the browser with a ``state`` of its own, so the panel does not mint the
    code. The operation checks the member and the business and
    answers the Hub's start (``/auth/login?next=``), which bounces to ``/hub-login/`` with its ``state``:
    that door mints the code, and asks for the second factor if the account has one."""

    def ready(self, hub):
        Hub.objects.filter(pk=hub.pk).update(
            status=Hub.Status.ACTIVE, ready_at=timezone.now()
        )

    def test_it_answers_the_hubs_start_and_mints_no_code(self, business, owner):
        self.ready(business)

        opened = services.opening.business_open(
            ctx_for(owner), BusinessOpenIn(id=business.id, next="/sales")
        )

        assert opened.url == "http://bar-manolo.localhost:8000/auth/login?next=/sales"
        assert not AuthExchangeCode.objects.exists()

    def test_in_production_it_is_the_businesss_own_host(self, business, owner, settings):
        settings.HUB_CALLBACK_TEMPLATE = "https://{slug}.erplora.com/auth/callback"
        self.ready(business)

        opened = services.opening.business_open(ctx_for(owner), BusinessOpenIn(id=business.id))

        assert opened.url == "https://bar-manolo.erplora.com/auth/login?next=/"

    def test_it_remembers_the_business_last_opened(self, business, owner):
        self.ready(business)

        services.opening.business_open(ctx_for(owner), BusinessOpenIn(id=business.id))

        assert (
            HubMember.objects.get(hub=business, user=owner).last_opened_at is not None
        )

    @pytest.mark.parametrize("who", ["admin", "manager", "employee"])
    def test_every_role_opens(self, business, team, who):
        self.ready(business)

        assert services.opening.business_open(
            ctx_for(team[who]), BusinessOpenIn(id=business.id)
        ).url.endswith("/auth/login?next=/")

    @pytest.mark.parametrize("who", ["stranger", "invitee"])
    def test_without_access_there_is_nothing_to_open(self, business, team, who):
        """An invitation is accepted first («Accept and enter»)."""
        self.ready(business)

        with pytest.raises(NotFound):
            services.opening.business_open(ctx_for(team[who]), BusinessOpenIn(id=business.id))

    @pytest.mark.parametrize(
        "status, code",
        [
            ("preparing", "hubs.business_preparing"),
            ("suspended", "hubs.business_suspended"),
            ("deleting", "hubs.business_deleted"),
        ],
    )
    def test_a_business_that_cannot_serve_says_why(self, business, owner, status, code):
        Hub.objects.filter(pk=business.pk).update(status=status)

        with pytest.raises(Conflict) as refused:
            services.opening.business_open(ctx_for(owner), BusinessOpenIn(id=business.id))

        assert refused.value.code == code
        assert HubMember.objects.get(hub=business, user=owner).last_opened_at is None

    def test_a_payment_pending_business_still_opens(self, business, owner):
        """7 days of grace with «Open» enabled and a notice."""
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.PAST_DUE)

        assert services.opening.business_open(
            ctx_for(owner), BusinessOpenIn(id=business.id)
        ).url

    def test_the_second_factor_is_asked_where_the_code_is_minted(
        self, business, owner, settings, monkeypatch
    ):
        """``/hub-login/`` sends an account with an authenticator app to confirm it (``reauthenticate``)
        before it mints the code; «Open» no longer refuses it on its own."""
        settings.ACCOUNTS_MFA_ENABLED = True
        self.ready(business)
        from accounts.queries import two_factor

        monkeypatch.setattr(two_factor, "has_totp", lambda user: True)

        assert services.opening.business_open(ctx_for(owner), BusinessOpenIn(id=business.id)).url
        assert not AuthExchangeCode.objects.exists()

    def test_from_the_installed_app_the_jump_carries_the_shell_mark(self, business, owner):
        """HUBS-F12: the app
        links the till to a hub only when a navigation with ``?shell=1`` leaves an entry page of the SaaS
        (``ERPlora/app`` ``hub_link.rs``), so its «Open» starts the jump with the mark."""
        self.ready(business)

        opened = services.opening.business_open(
            ctx_for(owner), BusinessOpenIn(id=business.id, next="/sales", shell=True)
        )

        assert opened.url == "http://bar-manolo.localhost:8000/auth/login?next=/sales&shell=1"

    def test_the_web_jump_carries_no_shell_mark(self, business, owner):
        self.ready(business)

        assert "shell" not in services.opening.business_open(ctx_for(owner), BusinessOpenIn(id=business.id)).url

    def test_next_is_a_path_of_the_business(self):
        for wrong in ("https://evil.example", "//evil.example", "sales"):
            with pytest.raises(Exception):
                BusinessOpenIn(id="0199a000-0000-7000-8000-000000000000", next=wrong)
