"""Guardrails of billing (the guardrails of django-ninja-live; CLAUDE.md, one road to the server).

- Only ``services`` and ``queries`` touch the database: the VAT engine (``vat.py``), the VIES
  client (``vies.py``), the Stripe mapping (``stripe_tax_rates.py``), the routes, schemas and events
  call them. Allowed besides: ``models`` (the singletons' ``save``), ``admin.py`` (Django's admin),
  the migrations and the seed loader (``seed.py`` with the models it is handed, and the command that
  runs it). ``services``, ``queries``, ``models`` and ``admin`` are each a file or a package one level deep.
- Nowhere ``using=``, ``.using(`` nor ``connections[``: one database (the SaaS has no tenancy).
- The network: only ``vies.py`` talks to VIES (``requests``) and only ``stripe_service.py`` to Stripe:
  it is the one door (keys, timeouts, errors, plain dicts), the one place tests replace
  (``billing/tests/stripe_double.py``).
- The tests replace ``stripe_service.client`` and nothing else, so every module of the SaaS asks
  ``stripe_service`` for the client at each call (``stripe_service.client()``): one that imported it by name,
  or kept it aside, would talk to the real Stripe in the tests.

Each scan is shown to catch its positive (rule 10 of the working rules: the control catches it).
"""

import ast
from pathlib import Path

from django.apps import apps
from django.conf import settings

BILLING = Path(settings.BASE_DIR) / "billing"
DATABASE_FILES = {
    "services.py",
    "queries.py",
    "models.py",
    "admin.py",
    "seed.py",
    "management/commands/seed_tax_rules.py",
}
DATABASE_PACKAGES = {"services", "queries", "models", "admin"}
DATABASE_NAMES = {"connection", "connections", "transaction"}
DATABASE_ATTRIBUTES = {
    "objects",
    "select_for_update",
    "cursor",
    "atomic",
    "on_commit",
    "raw",
    "save",
    "delete",
}


def code_files() -> list[Path]:
    return sorted(
        path
        for path in BILLING.rglob("*.py")
        if "tests" not in path.relative_to(BILLING).parts
        and "migrations" not in path.relative_to(BILLING).parts
    )


def _stripe_sdk(node: ast.Attribute) -> bool:
    """``client().v1.<service>.<method>``: a call to Stripe through ``stripe_service.client()``, not the ORM. Outside
    ``stripe_service`` it is written ``stripe_service.client()``."""
    root = node.value
    while isinstance(root, ast.Attribute):
        root = root.value
    if not isinstance(root, ast.Call):
        return False
    func = root.func
    if isinstance(func, ast.Name):
        return func.id == "client"
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "client"
        and isinstance(func.value, ast.Name)
        and func.value.id == "stripe_service"
    )


def database_touches(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in DATABASE_ATTRIBUTES and not _stripe_sdk(node):
            found.append(f"line {node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Name) and node.id in DATABASE_NAMES:
            found.append(f"line {node.lineno}: {node.id}")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "django.db"
            and any(a.name in DATABASE_NAMES for a in node.names)
        ):
            found.append(f"line {node.lineno}: from django.db import …")
    return found


def other_databases(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "using":
            found.append(f"line {node.value.lineno}: using=")
        elif isinstance(node, ast.Attribute) and node.attr == "using":
            found.append(f"line {node.lineno}: .using(")
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "connections"
        ):
            found.append(f"line {node.lineno}: connections[")
    return found


def imported_modules(source: str) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def saas_code_files() -> list[Path]:
    """The code of every app of the SaaS, its tests and migrations aside."""
    root = Path(settings.BASE_DIR).resolve()
    folders = {Path(config.path).resolve() for config in apps.get_app_configs()}
    return sorted(
        path
        for folder in folders
        if folder.parent == root
        for path in folder.rglob("*.py")
        if not {"tests", "migrations"} & set(path.relative_to(folder).parts)
    )


def _gateway_names(tree: ast.AST) -> set[str]:
    """What a module calls ``billing.stripe_service``: ``stripe_service``, its ``as`` name or the dotted path."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names |= {alias.asname or alias.name for alias in node.names if alias.name == "stripe_service"}
        elif isinstance(node, ast.Import):
            names |= {alias.asname or alias.name for alias in node.names if alias.name == "billing.stripe_service"}
    return names


def _names_the_client(node: ast.AST, gateway_names: set[str], *, gateway: bool) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "client" and ast.unparse(node.value) in gateway_names
    return gateway and isinstance(node, ast.Name) and node.id == "client"


def client_kept_aside(source: str, *, gateway: bool = False) -> list[str]:
    """Where ``source`` reaches Stripe's client other than by calling ``stripe_service.client()`` there and then:
    importing it by name, or keeping it in a variable, a default or a list. ``gateway``: ``source`` is
    ``stripe_service.py`` itself, where the client is the bare name ``client``."""
    tree = ast.parse(source)
    gateway_names = _gateway_names(tree)
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("stripe_service"):
            found += [f"line {node.lineno}: imports {alias.name}" for alias in node.names if alias.name in {"client", "*"}]
        elif id(node) not in called and _names_the_client(node, gateway_names, gateway=gateway):
            found.append(f"line {node.lineno}: {ast.unparse(node)} is not called there and then")
    return found


def _relative(path: Path) -> str:
    return path.relative_to(BILLING).as_posix()


def may_touch_the_database(relative: str) -> bool:
    parts = relative.split("/")
    return relative in DATABASE_FILES or (len(parts) == 2 and parts[0] in DATABASE_PACKAGES)


def test_the_scans_catch_their_positive():
    assert database_touches(
        "from django.db import transaction\nVatCheck.objects.all()\nrow.save()"
    )
    assert database_touches("profile.delete()\nBillingProfile.objects.filter(pk=1).delete()")
    # Stripe's SDK, reached through ``client()`` (``stripe_service.delete_customer``), is not the ORM.
    assert database_touches("client().v1.customers.delete('cus_1')") == []
    assert database_touches("stripe_service.client().v1.customers.tax_ids.delete('cus_1', 'txi_1')") == []
    assert database_touches("other.client().v1.customers.delete('cus_1')")
    assert other_databases(
        "Model.objects.using('other')\nconnections['x']\nqs.get(using='y')"
    )
    assert imported_modules("import stripe\nfrom requests import post") == {
        "stripe",
        "requests",
    }


def test_there_is_code_to_scan():
    names = {_relative(path) for path in code_files()}

    assert {"vat.py", "vies.py", "api.py"} <= names
    assert {"services.py", "services/__init__.py"} & names
    assert {"queries.py", "queries/__init__.py"} & names


def test_a_module_of_a_packaged_door_may_touch_the_database():
    assert may_touch_the_database("queries.py")
    assert may_touch_the_database("queries/invoices.py")
    assert may_touch_the_database("services/checkout.py")
    assert may_touch_the_database("models/tax.py")
    assert may_touch_the_database("admin/invoices.py")
    assert not may_touch_the_database("vat.py")
    assert not may_touch_the_database("queries/reports/csv.py")
    assert not may_touch_the_database("emails/queries.py")


def test_only_services_and_queries_touch_the_database():
    offenders = {
        _relative(path): touches
        for path in code_files()
        if not may_touch_the_database(_relative(path))
        and (touches := database_touches(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}


def test_nothing_names_another_database():
    offenders = {
        _relative(path): found
        for path in code_files()
        if (found := other_databases(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}


def test_only_the_vies_client_and_the_stripe_gateway_talk_to_the_network():
    importers = {
        _relative(path): imported_modules(path.read_text(encoding="utf-8"))
        for path in code_files()
    }

    assert [name for name, modules in importers.items() if "requests" in modules] == [
        "vies.py"
    ]
    assert [name for name, modules in importers.items() if "stripe" in modules] == [
        "stripe_service.py"
    ]


def test_the_client_scan_catches_its_positive():
    assert client_kept_aside("from billing.stripe_service import client\nclient().v1.refunds.create()")
    assert client_kept_aside("from billing.stripe_service import client as stripe_client")
    assert client_kept_aside("from billing.stripe_service import *")
    assert client_kept_aside("from billing import stripe_service\nmake = stripe_service.client")
    assert client_kept_aside("from billing import stripe_service as gateway\ndef pay(make=gateway.client): ...")
    assert client_kept_aside("import billing.stripe_service\nmakers = [billing.stripe_service.client]")
    assert client_kept_aside("make = client", gateway=True)
    assert client_kept_aside("from billing import stripe_service\nstripe_service._call(stripe_service.client().v1.x)") == []
    assert client_kept_aside("from billing.stripe_service import StripeRefused, key_mode") == []
    assert client_kept_aside("_call(client().v1.refunds.create)", gateway=True) == []
    assert client_kept_aside("from billing import stripe_service\nclient = other.client") == []


def test_every_module_asks_stripe_service_for_the_client_at_each_call():
    gateway = (BILLING / "stripe_service.py").resolve()
    files = saas_code_files()
    offenders = {
        path.relative_to(gateway.parent.parent).as_posix(): found
        for path in files
        if (found := client_kept_aside(path.read_text(encoding="utf-8"), gateway=path == gateway))
    }

    assert gateway in files
    assert offenders == {}
