"""System checks of apps: ``Module.slug`` points at an app of the catalog (spec §5.4).

``Module.slug`` has no database FK to ``shared.app`` (nothing crosses the ``shared`` schema), so
what an FK would do elsewhere is done by ``Module.clean()`` (the admin) and by ``apps.E001``,
which looks at the data: it catches what skipped ``clean()``, a data load or a script. It is a
database check, so it runs only when the database is named: ``manage.py check --database
default``, which the ``saas-migrate`` task runs after ``migrate`` (spec §11).
"""

from django.core import checks
from django.db import DEFAULT_DB_ALIAS, connection
from django.db.migrations.recorder import MigrationRecorder

from apps.models import App, Module

#: The last migration of apps: before it, the tables the check reads do not exist yet.
LAST_MIGRATION = ("apps", "0002_module")


@checks.register(checks.Tags.database)
def check_module_slugs(
    app_configs=None, databases=None, **kwargs
) -> list[checks.CheckMessage]:
    if not databases or DEFAULT_DB_ALIAS not in databases:
        return []
    # `migrate` runs the database checks before it migrates: on a new database the tables of
    # apps are not there yet, and this check must not stop the migration that creates them.
    if LAST_MIGRATION not in MigrationRecorder(connection).applied_migrations():
        return []
    dangling = list(
        Module.objects.exclude(slug__in=App.objects.values("id"))
        .order_by("slug")
        .values_list("slug", flat=True)
    )
    if not dangling:
        return []
    return [
        checks.Error(
            f"Module rows without an app in shared.app: {', '.join(dangling)}.",
            hint=(
                "Every Module.slug is the label of a paid app the Hub registered (register_apps). "
                "Fix the slug in the admin, or register the Hub's release that brings the app."
            ),
            obj=Module,
            id="apps.E001",
        )
    ]
