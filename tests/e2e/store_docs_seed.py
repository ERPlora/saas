"""The app the store's e2e opens (store-docs.spec.ts): seeded before the run, removed after it.

``uv run python tests/e2e/store_docs_seed.py seed|clear`` from saas-next/, against the local
database of ``.env``. The rows are the ones the Hub's ``register_apps`` would write
(``apps/tests/factories.py``): a listed app whose Spanish documentation holds a Mermaid diagram, and
no English one, so the page also shows the «only in Spanish» notice; it requires a premium app, so
its overview also paints the «Required apps» card.
"""

import os
import sys
from pathlib import Path

SAAS_DIR = Path(__file__).resolve().parents[2]
APP_ID = "e2e_store_docs"
REQUIRED_ID = "e2e_store_base"
DOC = """# Documentación de prueba

Un diagrama del flujo de una venta:

```mermaid
graph TD
    Ticket[Ticket abierto] --> Cobro[Cobro]
    Cobro --> Factura[Factura VeriFactu]
```
"""


def main(action: str) -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from apps.models import App, AppDoc
    from apps.tests.factories import make_app, make_doc

    AppDoc.objects.filter(app_id__in=[APP_ID, REQUIRED_ID]).delete()
    App.objects.filter(pk__in=[APP_ID, REQUIRED_ID]).delete()
    if action == "seed":
        make_app(
            REQUIRED_ID,
            name_en="E2E Store Base",
            name_es="E2E Base",
            category="sales",
            premium=True,
        )
        app = make_app(
            APP_ID,
            name_en="E2E Store Docs",
            name_es="E2E Documentación",
            category="organization",
            requires=[REQUIRED_ID],
        )
        make_doc(app, "es", DOC)
    print(f"{action}: {APP_ID}, {REQUIRED_ID}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"seed", "clear"}:
        sys.exit("usage: store_docs_seed.py seed|clear")
    main(sys.argv[1])
