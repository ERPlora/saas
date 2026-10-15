"""System checks of hubs: ``hubs.W001``, the jump's access (``accounts.HubMembership``) disagrees with the
answered members of the businesses (``hubs.queries.verify_access_mirror``; plan 2026-10-13, L1-A2).

A database check: it runs with ``manage.py check --database default`` (and ``migrate``, which asks with its
database), never in a plain ``check`` or ``check --deploy``. A warning, so a disagreement never stops a
migration that would fix it; ``--fail-level WARNING`` turns it into a failure.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import SystemCheckError

from accounts.models import HubMembership

pytestmark = pytest.mark.django_db


class TestTheSystemCheck:
    def check(self, *args):
        out, err = StringIO(), StringIO()
        call_command("check", *args, stdout=out, stderr=err)
        return out.getvalue() + err.getvalue()

    def test_with_the_database_a_disagreement_is_a_warning(self, owner):
        HubMembership.objects.create(user=owner, hub_slug="seed-hub", role="hub_owner")

        output = self.check("--database", "default")

        assert "hubs.W001" in output
        assert "seed-hub" in output

    def test_it_fails_the_check_at_the_warning_level(self, owner):
        HubMembership.objects.create(user=owner, hub_slug="seed-hub", role="hub_owner")

        with pytest.raises(SystemCheckError, match="hubs.W001"):
            self.check("--database", "default", "--fail-level", "WARNING")

    def test_agreeing_tables_say_nothing(self, business, team):
        assert "hubs.W001" not in self.check("--database", "default")

    def test_without_the_database_it_does_not_run(self, owner):
        """``manage.py check`` (and ``check --deploy``) reads no table; ``migrate`` asks with its database."""
        HubMembership.objects.create(user=owner, hub_slug="seed-hub", role="hub_owner")

        assert "hubs.W001" not in self.check()


def test_it_skips_while_hubs_has_migrations_to_apply(owner):
    """``migrate`` runs the database checks before migrating: with migrations of hubs or accounts still to
    apply (the data migration that fills the mirror among them) the check says nothing, so it never
    stands in the way of the migration that fixes the disagreement.

    The plans are in the database (``hubs/0013``), so going forward the adoption gives the business its Free
    subscription: the foreign key checks run at once, as each migration's own COMMIT does, or one still pending
    in the test's transaction stops a later migration from altering ``hubs_subscription``."""
    from django.db import connection

    from hubs import checks, queries

    HubMembership.objects.create(user=owner, hub_slug="seed-hub", role="hub_owner")
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    call_command("migrate", "hubs", "0005", verbosity=0)
    try:
        assert queries.mirror_migrated() is False
        assert checks.access_mirror(None, databases=["default"]) == []
    finally:
        call_command("migrate", "hubs", verbosity=0)
    assert queries.mirror_migrated() is True
