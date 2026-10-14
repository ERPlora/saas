"""System checks of hubs.

``hubs.W001``: the access the jump to a hub reads (``accounts.HubMembership``) disagrees with the answered
members of the businesses (``hubs.queries.verify_access_mirror``; plan 2026-10-13, L1-A2). A database check:
``manage.py check --database default`` runs it, and so does ``migrate`` with its database; a plain
``check`` or ``check --deploy`` reads no table. A warning, never an error, so it never stops the migration
that fixes the disagreement; and it says nothing while hubs or accounts have migrations to apply.
"""

from django.core import checks
from django.db import DEFAULT_DB_ALIAS

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

