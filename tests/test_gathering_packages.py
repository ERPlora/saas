"""A door split into one module per entity only gathers its modules in its ``__init__``; one still being split keeps
code of its own there, but takes each of its modules whole all the same.

A name re-exported from the ``__init__`` would give every operation two import paths again, and a patch through the
package would no longer reach the module that reads the name. A package that re-exports on purpose (``billing``'s, and
an app's ``models``, whose migrations name ``<app>.models.<name>``) is not listed here.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings

#: The packages nothing is re-exported from: a name is imported from its own module.
GATHERING_PACKAGES = ("accounts.services", "hubs.queries", "hubs.schemas", "hubs.services")
#: The packages still being split: their ``__init__`` holds code of its own, but re-exports nothing either.
SPLITTING_PACKAGES = ("billing.services",)


def _takes_whole_modules(node: ast.stmt, package: str, modules: set[str]) -> bool:
    """``from <package> import <module>, …``: each module whole, under its own name."""
    return (
        isinstance(node, ast.ImportFrom)
        and node.level == 0
        and node.module == package
        and all(alias.name in modules and alias.asname is None for alias in node.names)
    )


def statements_beyond_gathering(source: str, package: str, modules: set[str]) -> list[str]:
    """What an ``__init__`` holds besides its docstring and ``from <package> import <module>``."""
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if not _takes_whole_modules(node, package, modules):
            found.append(f"line {node.lineno}: {ast.unparse(node)}")
    return found


def _imports_from_its_package(node: ast.stmt, package: str) -> bool:
    """An import of an ``__init__`` from its own package, spelled in full or relative (``from .module import name``)."""
    return isinstance(node, ast.ImportFrom) and (
        node.level > 0 or node.module == package or (node.module or "").startswith(f"{package}.")
    )


def _renames_a_name_of_a_module(node: ast.stmt, modules: set[str]) -> bool:
    """``name = <module>.<name>``: the re-export that needs no import."""
    value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
    if not isinstance(value, ast.Attribute):
        return False
    while isinstance(value, ast.Attribute):
        value = value.value
    return isinstance(value, ast.Name) and value.id in modules


def names_taken_from_its_modules(source: str, package: str, modules: set[str]) -> list[str]:
    """What gives a name of a module a second path in the ``__init__`` of its package: an import from the package that
    takes anything but whole modules, and a name of a module assigned to a name of the ``__init__``."""
    return [
        f"line {node.lineno}: {ast.unparse(node)}"
        for node in ast.parse(source).body
        if (_imports_from_its_package(node, package) and not _takes_whole_modules(node, package, modules))
        or _renames_a_name_of_a_module(node, modules)
    ]


def _modules_of(package: str) -> tuple[Path, set[str]]:
    folder = Path(settings.BASE_DIR).joinpath(*package.split("."))
    return folder, {path.stem for path in folder.glob("*.py")} - {"__init__"}


@pytest.mark.parametrize("package", GATHERING_PACKAGES)
def test_the_package_only_gathers_its_modules(package):
    folder, modules = _modules_of(package)

    assert modules, f"{package} has no modules"
    assert statements_beyond_gathering((folder / "__init__.py").read_text(), package, modules) == []


def test_the_scan_catches_a_re_exported_name_and_code_of_its_own():
    source = (
        '"""Docstring."""\n'
        "from hubs.queries import taxonomy\n"
        "from hubs.queries.plan_catalog import free_plan\n"
        "from hubs.queries.taxonomy import *\n"
        "from hubs.queries import taxonomy as groups\n"
        "from hubs.queries import missing\n"
        "LIMIT = 3\n"
    )

    assert statements_beyond_gathering(source, "hubs.queries", {"taxonomy", "plan_catalog"}) == [
        "line 3: from hubs.queries.plan_catalog import free_plan",
        "line 4: from hubs.queries.taxonomy import *",
        "line 5: from hubs.queries import taxonomy as groups",
        "line 6: from hubs.queries import missing",
        "line 7: LIMIT = 3",
    ]


@pytest.mark.parametrize("package", SPLITTING_PACKAGES)
def test_a_package_still_being_split_takes_its_modules_whole(package):
    folder, modules = _modules_of(package)

    assert modules, f"{package} has no modules"
    assert names_taken_from_its_modules((folder / "__init__.py").read_text(), package, modules) == []


def test_the_scan_catches_a_name_taken_from_a_module_but_not_the_code_around_it():
    source = (
        '"""Docstring."""\n'
        "from billing import queries, vat\n"
        "from billing.services import sale_tax, vat_clearance\n"
        "from billing.services.sale_tax import sale_quote\n"
        "from billing.services import clear_tax_id_for_stripe\n"
        "from billing.services import sale_tax as taxes\n"
        "from hubs.services import refusals\n"
        "LIMIT = 3\n"
        "from .sale_tax import sale_quote\n"
        "from . import vat_clearance\n"
        "sale_quote = sale_tax.sale_quote\n"
        "INVALID: str = vat_clearance.CLEARANCE_INVALID\n"
        "quote = sale_tax.sale_quote(None)\n"
    )

    assert names_taken_from_its_modules(source, "billing.services", {"sale_tax", "vat_clearance"}) == [
        "line 4: from billing.services.sale_tax import sale_quote",
        "line 5: from billing.services import clear_tax_id_for_stripe",
        "line 6: from billing.services import sale_tax as taxes",
        "line 9: from .sale_tax import sale_quote",
        "line 10: from . import vat_clearance",
        "line 11: sale_quote = sale_tax.sale_quote",
        "line 12: INVALID: str = vat_clearance.CLEARANCE_INVALID",
    ]
