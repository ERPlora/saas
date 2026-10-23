"""ACCOUNTS-F36 · The audit trail of the account models (django-auditlog; PLAN-SAAS §1.1: «SE PORTA django-auditlog»).

Ported from ERPlora/saas ``apps/auth/users/auditlog.py`` and ``tests/unit/test_auditlog_coverage.py`` (#970): who
changed an account, its access to a business, its API keys and its signed-in sessions, from which address, with
the secrets never written (#957: without ``serialize_auditlog_fields_only`` the excluded password hash leaked into
the serialized blob). Changed: the address is the one ``public.client_ip`` resolved behind the ALB, not the first
``X-Forwarded-For`` entry the visitor may type; the actor is whoever the request acts as when the change is written,
so a write through an API key (whose account ``accounts.api_auth`` sets after the middleware ran) has its actor too;
the fields that move on every request (``last_login``, a key's ``last_used_at``, a session's ``last_seen_at``) are
not logged, the sign-in itself is (the session row). The billing and fiscal models are their apps'.
"""

import re
from datetime import timedelta

import pytest
from allauth.usersessions.models import UserSession
from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone, translation
from django.utils.formats import date_format

from accounts.auditlog import AuditActorMiddleware
from accounts.models import ApiKey, HubMembership
from accounts.tests.conftest import api_post
from hubs.tests.conftest import plans  # noqa: F401 - the plans fixture

pytestmark = pytest.mark.django_db

PROFILE = "/api/accounts/profile"
KEYS = "/api/accounts/api-keys"


def _entries_for(instance):
    return LogEntry.objects.get_for_object(instance)


def _everything_written(entries) -> str:
    """All a log entry keeps about its object, as one string to search for a secret."""
    return " ".join(
        f"{entry.object_repr} {entry.changes} {entry.changes_text} {entry.serialized_data} {entry.additional_data}"
        for entry in entries
    )


class TestWhatIsAudited:
    def test_the_account_models_are_registered(self):
        """A model that lets someone in (the account, its businesses, its keys, its sessions) leaves a trail."""
        registered = {model.__name__ for model in auditlog.get_models()}

        assert {"User", "HubMembership", "ApiKey", "UserSession"} <= registered

    def test_a_change_to_the_account_is_logged_with_what_changed(self, ana):
        ana.first_name = "Ana María"
        ana.save()

        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).get()
        assert entry.changes_dict["first_name"] == ["Ana", "Ana María"]

    def test_a_new_account_is_logged_with_its_own_fields_not_the_rows_that_point_at_it(self, ana):
        """auditlog drops only many-to-many relations: a new account listed «Api keys: None → accounts.ApiKey.None»,
        «Billing profiles», «Hub members»… among its «changes», the managers of the rows of other models that point
        at it. Those rows have their own entries; the account's say what the account is."""
        created = _entries_for(ana).get(action=LogEntry.Action.CREATE)
        reverse = {field.name for field in get_user_model()._meta.get_fields() if field.auto_created and not field.concrete}

        assert "email" in created.changes_dict
        assert reverse and not reverse & set(created.changes_dict)
        assert ".None" not in str(created.changes)

    def test_access_to_a_business_is_logged(self, ana):
        membership = HubMembership.objects.create(user=ana, hub_slug="bar-pepe", role=HubMembership.Role.ADMIN)

        assert _entries_for(membership).filter(action=LogEntry.Action.CREATE).exists()


class TestNoSecretIsWritten:
    def test_the_password_hash_is_never_logged(self, ana):
        """#957: ``exclude_fields`` alone still put the hash in the serialized copy of the account."""
        ana.set_password("another long passphrase")
        ana.save()
        ana.first_name = "Anabel"
        ana.save()

        written = _everything_written(_entries_for(ana))
        assert ana.password not in written
        assert "password" not in written
        assert "first_name" in written

    def test_a_password_change_alone_writes_no_entry(self, ana):
        before = _entries_for(ana).count()

        ana.set_password("another long passphrase")
        ana.save()

        assert _entries_for(ana).count() == before

    def test_the_hash_of_an_api_key_is_never_logged(self, signed_in, ana):
        response = api_post(signed_in, KEYS, {"name": "Zapier", "scopes": ["hubs.read"]})
        assert response.status_code == 201
        key = ApiKey.objects.get(user=ana)

        entries = _entries_for(key)
        assert entries.filter(action=LogEntry.Action.CREATE).exists()
        written = _everything_written(entries)
        assert key.key_hash not in written
        assert response.json()["secret"] not in written

    def test_the_key_of_a_session_is_never_logged(self, signed_in, ana):
        session = UserSession.objects.get(user=ana)

        written = _everything_written(_entries_for(session))
        assert _entries_for(session).filter(action=LogEntry.Action.CREATE).exists()
        assert session.session_key not in written
        assert "session_key" not in written


class TestWhatMovesOnEveryRequestIsNotLogged:
    def test_using_an_api_key_writes_no_entry_and_revoking_it_does(self, ana):
        key = ApiKey.objects.create(user=ana, name="Zapier", prefix="erps_liv", key_hash="0" * 64, scopes=["hubs.read"])
        before = _entries_for(key).count()

        key.last_used_at = timezone.now()
        key.save()
        assert _entries_for(key).count() == before

        key.revoked_at = timezone.now()
        key.save()
        assert "revoked_at" in _entries_for(key).filter(action=LogEntry.Action.UPDATE).get().changes_dict

    def test_signing_in_again_does_not_log_the_account(self, ana):
        before = _entries_for(ana).count()

        ana.last_login = timezone.now()
        ana.save(update_fields=["last_login"])

        assert _entries_for(ana).count() == before

    def test_a_session_seen_again_writes_no_entry(self, signed_in, ana):
        session = UserSession.objects.get(user=ana)
        before = _entries_for(session).count()

        session.last_seen_at = timezone.now() + timedelta(minutes=10)
        session.save()

        assert _entries_for(session).count() == before


class TestWhoAndFromWhere:
    def test_a_change_from_the_panel_names_the_account_and_its_address(self, client, ana, settings):
        settings.TRUSTED_PROXY_HOPS = 0
        client.force_login(ana)

        response = api_post(client, PROFILE, {"first_name": "Ana", "last_name": "Gil"}, REMOTE_ADDR="10.0.0.7")

        assert response.status_code == 200
        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).latest("timestamp")
        assert (entry.actor, entry.actor_email) == (ana, "ana@example.com")
        assert entry.remote_addr == "10.0.0.7"

    def test_a_typed_forwarded_address_is_not_the_address(self, client, ana, settings):
        """Locally nothing sits in front: the peer is the address, whatever the request claims."""
        settings.TRUSTED_PROXY_HOPS = 0
        client.force_login(ana)

        api_post(
            client, PROFILE, {"first_name": "Ana", "last_name": "Gil"}, REMOTE_ADDR="10.0.0.7", HTTP_X_FORWARDED_FOR="6.6.6.6"
        )

        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).latest("timestamp")
        assert entry.remote_addr == "10.0.0.7"

    def test_behind_the_balancer_the_address_is_the_one_it_saw(self, client, ana, settings):
        """The ALB appends the visitor it talked to; what comes before it the visitor may have typed."""
        settings.TRUSTED_PROXY_HOPS = 1
        client.force_login(ana)

        api_post(
            client,
            PROFILE,
            {"first_name": "Ana", "last_name": "Gil"},
            REMOTE_ADDR="10.0.0.2",
            HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9",
        )

        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).latest("timestamp")
        assert entry.remote_addr == "203.0.113.9"

    def test_the_actor_is_whoever_the_request_acts_as_when_the_change_is_written(self, ana):
        """An API key's account is set on the request after the middleware ran (``accounts.api_auth``)."""
        request = RequestFactory().post("/api/hubs/x", REMOTE_ADDR="10.0.0.8")

        def view(request):
            request.user = ana
            ana.first_name = "Ana Key"
            ana.save()
            return HttpResponse()

        AuditActorMiddleware(view)(request)

        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).get()
        assert entry.actor == ana
        assert entry.remote_addr == "10.0.0.8"

    def test_after_signing_out_what_is_written_has_no_author(self, ana):
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().post("/api/accounts/profile/delete")

        def view(request):
            request.user = ana
            ana.first_name = "Signed in"
            ana.save()
            request.user = AnonymousUser()
            ana.first_name = "Signed out"
            ana.save()
            return HttpResponse()

        AuditActorMiddleware(view)(request)

        entries = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).order_by("timestamp")
        assert [entry.actor for entry in entries] == [ana, None]

    def test_an_anonymous_request_has_no_actor(self, ana):
        request = RequestFactory().post("/api/accounts/x")

        def view(request):
            from django.contrib.auth.models import AnonymousUser

            request.user = AnonymousUser()
            ana.first_name = "Nobody"
            ana.save()
            return HttpResponse()

        AuditActorMiddleware(view)(request)

        assert _entries_for(ana).filter(action=LogEntry.Action.UPDATE).get().actor is None


class TestAnAccountThatGoes:
    """What goes with an account is logged while the request may still act as it: those entries must not hold the
    account back (an entry's author is ``SET_NULL`` only for the entries there before the deletion started)."""

    def test_deleting_my_own_account_leaves_no_entry_pointing_at_it(self, signed_in, ana, plans):  # noqa: F811
        from django.db import connection
        from hubs.models import Hub
        from hubs.tests.conftest import create_business

        business = create_business(ana)
        Hub.objects.filter(pk=business.pk).update(status=Hub.Status.DELETING, deletion_requested_at=timezone.now())

        assert api_post(signed_in, "/api/accounts/profile/delete").status_code == 200

        connection.check_constraints()
        assert not LogEntry.objects.filter(actor_id=ana.pk).exists()
        assert LogEntry.objects.filter(object_pk=str(ana.pk), action=LogEntry.Action.DELETE).exists()

    def test_an_account_deleted_by_itself_without_signing_out_keeps_its_email_on_the_trail(self, ana):
        """The admin's «Delete» of one's own account: the request acts as the account until the end."""
        from django.db import connection

        membership = HubMembership.objects.create(user=ana, hub_slug="bar-pepe", role=HubMembership.Role.ADMIN)
        account_pk = ana.pk
        request = RequestFactory().post("/admin/accounts/user/x/delete/")

        def view(request):
            request.user = ana
            ana.delete()
            return HttpResponse()

        AuditActorMiddleware(view)(request)

        connection.check_constraints()
        for pk in (membership.pk, account_pk):
            gone = LogEntry.objects.get(object_pk=str(pk), action=LogEntry.Action.DELETE)
            assert (gone.actor_id, gone.actor_email) == (None, "ana@example.com")


class TestTheAdmin:
    def test_the_superuser_reads_the_trail_and_cannot_change_it(self, client, ana):
        ana.first_name = "Anabel"
        ana.save()
        root = get_user_model().objects.create_superuser(email="root@example.com", password="x")
        client.force_login(root)

        listing = client.get("/admin/auditlog/logentry/")
        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).get()
        detail = client.get(f"/admin/auditlog/logentry/{entry.pk}/change/")

        assert listing.status_code == 200
        assert "ana@example.com" in listing.content.decode()
        assert detail.status_code == 200
        assert client.get("/admin/auditlog/logentry/add/").status_code == 403

    def test_staff_without_the_permission_does_not_see_it(self, client):
        staff = get_user_model().objects.create_user(email="support@example.com", password="x", is_staff=True)
        client.force_login(staff)

        assert client.get("/admin/auditlog/logentry/").status_code == 403

    def test_its_list_says_what_changed_in_the_staffs_language(self, client, ana):
        """The package writes its summary («1 change: first_name») and the header «Correlation ID» in English whatever
        the language, and its «Resource Type» filter by the models' code names (``usersession``): the list in Spanish (the admin speaks the
        browser's language) says them in Spanish, each field and model by its name, as Django's own history does."""
        ana.first_name = "Anabel"
        ana.save()
        root = get_user_model().objects.create_superuser(email="root@example.com", password="x", language="es")
        client.force_login(root)
        user_type = LogEntry.objects.filter(object_pk=str(ana.pk)).values_list("content_type_id", flat=True).first()

        listing = client.get("/admin/auditlog/logentry/", HTTP_ACCEPT_LANGUAGE="es").content.decode()

        assert "1 cambio: Nombre" in listing
        assert "ID de correlación" in listing
        assert "1 change" not in listing and "Correlation ID" not in listing
        assert re.search(rf'href="\?resource_type={user_type}"[^>]*>\s*Usuario\s*<', listing)

    def test_an_entry_says_when_in_the_staffs_language(self, client, ana):
        """The list formats the date; the entry's page printed it raw («2026-10-23 11:46:10.268295+02:00»)."""
        ana.first_name = "Anabel"
        ana.save()
        root = get_user_model().objects.create_superuser(email="root@example.com", password="x", language="es")
        client.force_login(root)
        entry = _entries_for(ana).filter(action=LogEntry.Action.UPDATE).get()

        page = client.get(f"/admin/auditlog/logentry/{entry.pk}/change/", HTTP_ACCEPT_LANGUAGE="es").content.decode()

        with translation.override("es"):
            said = date_format(timezone.localtime(entry.timestamp), "DATETIME_FORMAT")
        assert said in page
        assert str(timezone.localtime(entry.timestamp)) not in page

    def test_its_list_in_english_counts_the_changes(self, client, ana):
        ana.first_name, ana.last_name = "Anabel", "Ruiz"
        ana.save()
        root = get_user_model().objects.create_superuser(email="root@example.com", password="x", language="en")
        client.force_login(root)

        listing = client.get("/admin/auditlog/logentry/", HTTP_ACCEPT_LANGUAGE="en").content.decode()

        assert re.search(r"2 changes: (First name, Last name|Last name, First name)", listing)
        assert "Correlation ID" in listing

    def test_its_labels_speak_spanish(self):
        """The package ships no Spanish: the project's catalog carries it («log entries» is Django's own)."""
        from django.apps import apps

        with translation.override("es"):
            assert str(apps.get_app_config("auditlog").verbose_name) == "Registro de auditoría"
            assert str(LogEntry._meta.verbose_name_plural) == "entradas de registro"
            assert str(dict(LogEntry.Action.choices)[LogEntry.Action.UPDATE]) == "modificación"
            assert str(LogEntry._meta.get_field("remote_addr").verbose_name) == "dirección remota"
