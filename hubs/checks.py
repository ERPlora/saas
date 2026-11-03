"""System checks of hubs.

``hubs.W001``: the access the jump to a hub reads (``accounts.HubMembership``) disagrees with the answered
members of the businesses (``hubs.queries.verify_access_mirror``; plan 2026-10-13, L1-A2). A database check:
``manage.py check --database default`` runs it, and so does ``migrate`` with its database; a plain
``check`` or ``check --deploy`` reads no table. A warning, never an error, so it never stops the migration
that fixes the disagreement; and it says nothing while hubs or accounts have migrations to apply.

``hubs.W002``: an account of ERPlora's staff is also on a business (``hubs.queries.staff_on_businesses``; W11b).
The doors refuse it now; this names what is left from before, and nothing is turned off by itself:
``hubs/README.md`` says how to put each right by hand. A database check and a warning, as ``hubs.W001`` and for
the same reason (``migrate`` runs it: an error would stop every deploy until then); ``--fail-level WARNING``
turns it into a failure.
"""

from django.core import checks
from django.db import DEFAULT_DB_ALIAS
from django.utils import timezone

#: Disagreements named in the message; the rest are counted.
SHOWN = 5


@checks.register(checks.Tags.database)
def access_mirror(app_configs, databases=None, **kwargs):
    if not databases or DEFAULT_DB_ALIAS not in databases:
        return []
    from hubs import queries

    if not queries.mirror_migrated():
        return []
    drift = queries.verify_access_mirror()
    if not drift:
        return []
    shown = "; ".join(
        f"{slug} / {user_id}: should be {should or 'absent'}, is {has or 'absent'}"
        for slug, user_id, should, has in drift[:SHOWN]
    )
    more = f" (and {len(drift) - SHOWN} more)" if len(drift) > SHOWN else ""
    return [
        checks.Warning(
            f"accounts.HubMembership disagrees with the members of the businesses in {len(drift)} row(s): {shown}{more}.",
            hint="Only hubs.services.sync_access writes accounts.HubMembership: find the write that went around it, "
            "then run sync_access for each business named here.",
            id="hubs.W001",
        )
    ]



@checks.register(checks.Tags.database)
def staff_on_a_business(app_configs, databases=None, **kwargs):
    if not databases or DEFAULT_DB_ALIAS not in databases:
        return []
    from hubs import queries

    if not queries.mirror_migrated():
        return []
    found = queries.staff_on_businesses(timezone.now())
    if not found:
        return []
    shown = "; ".join(f"{email} on {slug} ({how})" for email, slug, how in found[:SHOWN])
    more = f" (and {len(found) - SHOWN} more)" if len(found) > SHOWN else ""
    return [
        checks.Warning(
            f"{len(found)} account(s) of ERPlora's staff are also on a business: {shown}{more}.",
            hint="ERPlora's staff and the customers never share an account. Put each right by hand (hubs/README.md, "
            "«Personal en un negocio»): lower «Staff status» and «Superuser status» on its page of the admin, or take "
            "it off the business (remove the member, withdraw the invitation; an owner transfers it first).",
            id="hubs.W002",
        )
    ]
