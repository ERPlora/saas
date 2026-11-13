"""System checks of hubs.

``hubs.W002``: an account of ERPlora's staff is also on a business (``hubs.queries.staff_on_businesses``).
The doors refuse it now; this names what is left from before, and nothing is turned off by itself:
``hubs/README.md`` says how to put each right by hand. A database check: ``manage.py check --database default`` runs
it, and so does ``migrate`` with its database; a plain ``check`` or ``check --deploy`` reads no table. A warning, never
an error (``migrate`` runs it: an error would stop every deploy until then), and it says nothing while hubs or accounts
have migrations to apply; ``--fail-level WARNING`` turns it into a failure.
"""

from django.core import checks
from django.db import DEFAULT_DB_ALIAS
from django.utils import timezone

#: Accounts named in the message; the rest are counted.
SHOWN = 5


@checks.register(checks.Tags.database)
def staff_on_a_business(app_configs, databases=None, **kwargs):
    if not databases or DEFAULT_DB_ALIAS not in databases:
        return []
    from hubs import queries

    if not queries.tables_migrated():
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
