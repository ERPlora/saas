"""An app's ``services``, ``queries``, ``models`` and ``admin`` are each a file or a package one level deep
(``billing/queries/invoices.py``), and a package keeps the shape that makes splitting a file safe.

- Importing a module of the package is what registers its operations, its models or its admins, so the package's
  ``__init__.py`` imports every module by name, and nothing uses ``import *``, which hides what each module declares.
- One level: no package inside the package.
- Its modules never import each other around a loop at their top level. An import inside a function waits for a
  call, so it is the way out of a loop, with a comment saying why.
- What the rest of the code reads from the package (``from billing.queries import x``, ``queries.x``) is there.

Each scan is shown to catch its positive.
"""

import ast
import importlib
import os
from pathlib import Path

from django.apps import apps
from django.conf import settings

REPO = Path(settings.BASE_DIR).resolve()
PACKAGES = ("services", "queries", "models", "admin")
# Not the SaaS's code: dependencies, the live and ui submodules and git's own files.
SKIPPED_DIRS = frozenset({".venv", "node_modules", "packages", ".git", "__pycache__"})


def app_folders(root: Path = REPO) -> list[Path]:
    """The folders of the SaaS's own apps, at the top of the repository."""
    folders = (Path(config.path).resolve() for config in apps.get_app_configs())
    return sorted(folder for folder in folders if folder.parent == root)


def door_packages(root: Path = REPO) -> list[Path]:
    return [folder / name for folder in app_folders(root) for name in PACKAGES if (folder / name).is_dir()]


def dotted(folder: Path, root: Path = REPO) -> str:
    return ".".join(folder.relative_to(root).parts)


def _imported(node: ast.ImportFrom, package: str) -> list[str]:
    if node.level == 1:
        return [node.module.split(".")[0]] if node.module else [alias.name for alias in node.names]
    if node.level == 0 and node.module == package:
        return [alias.name for alias in node.names]
    if node.level == 0 and node.module and node.module.startswith(f"{package}."):
        return [node.module.removeprefix(f"{package}.").split(".")[0]]
    return []


def own_imports(source: str, package: str) -> set[str]:
    """The names of ``package`` (dotted) that ``source`` imports at its top level, where an import runs as the
    module loads: ``from . import a``, ``from .a import x``, ``from shop.queries import a`` and
    ``from shop.queries.a import x`` all import the module ``a``."""
    return {
        name
        for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom)
        for name in _imported(node, package)
    }


def star_imports(source: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
    ]


def import_loop(graph: dict[str, set[str]]) -> list[str]:
    """A loop in ``graph`` (module → the modules it imports) as the path that closes it, or ``[]``."""
    finished: set[str] = set()

    def visit(name: str, path: list[str]) -> list[str]:
        if name in path:
            return [*path[path.index(name) :], name]
        if name in finished:
            return []
        for imported in sorted(graph[name]):
            if loop := visit(imported, [*path, name]):
                return loop
        finished.add(name)
        return []

    for name in sorted(graph):
        if loop := visit(name, []):
            return loop
    return []


def package_problems(folder: Path, package: str) -> list[str]:
    """What breaks the shape of the package at ``folder``, whose dotted name is ``package``."""
    if not (folder / "__init__.py").is_file():
        return [f"{package} has no __init__.py: nothing imports its modules, so they register nothing"]
    sources = {path.stem: path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.py"))}
    modules = set(sources) - {"__init__"}
    problems = [
        f"{package}.{inner.name} is a package inside the package: make it a module of {package}"
        for inner in sorted(folder.iterdir())
        if inner.is_dir() and any(inner.rglob("*.py"))
    ]
    problems += [
        f"{package}.{name} line {line}: import *, which hides what each module declares"
        for name, source in sources.items()
        for line in star_imports(source)
    ]
    problems += [
        f"{package}.{name} is never imported by its __init__.py, so it registers nothing: add `from . import {name}`"
        for name in sorted(modules - own_imports(sources["__init__"], package))
    ]
    if loop := import_loop({name: own_imports(sources[name], package) & modules for name in modules}):
        problems.append(f"{package}: its modules import each other around a loop: {' → '.join(loop)}")
    return problems


def names_read(source: str, package: str) -> set[str]:
    """The names ``source`` reads from ``package`` (dotted): ``from shop.queries import x``, and ``q.x`` after
    ``from shop import queries as q`` or ``shop.queries.x`` after ``import shop.queries``."""
    app, door = package.rsplit(".", 1)
    tree = ast.parse(source)
    names: set[str] = set()
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == package:
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == app:
            aliases |= {alias.asname or alias.name for alias in node.names if alias.name == door}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id in aliases:
            names.add(node.attr)
        elif ast.unparse(node.value) == package:
            names.add(node.attr)
    return names


def python_files(root: Path = REPO) -> list[Path]:
    """The SaaS's Python files, relative to ``root``."""
    found = []
    for folder, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in SKIPPED_DIRS]
        found += [Path(folder, name).relative_to(root) for name in files if name.endswith(".py")]
    return sorted(found)


def _package(root: Path, files: dict[str, str]) -> Path:
    folder = root / "shop" / "queries"
    for name, source in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(source)
    return folder


def test_a_package_in_shape_has_no_problem(tmp_path):
    folder = _package(
        tmp_path,
        {
            "__init__.py": "from . import order\nfrom shop.queries.stock import level\n",
            "order.py": "from shop.queries.stock import level\n\ndef total():\n    return level()\n",
            "stock.py": "def level():\n    from shop.queries import order  # inside a function: no loop\n",
        },
    )

    assert package_problems(folder, "shop.queries") == []


def test_a_package_without_its_init_is_caught(tmp_path):
    folder = _package(tmp_path, {"order.py": ""})

    assert package_problems(folder, "shop.queries") == [
        "shop.queries has no __init__.py: nothing imports its modules, so they register nothing"
    ]


def test_a_module_its_init_never_imports_is_caught(tmp_path):
    folder = _package(tmp_path, {"__init__.py": "from . import order\n", "order.py": "", "stock.py": ""})

    assert package_problems(folder, "shop.queries") == [
        "shop.queries.stock is never imported by its __init__.py, so it registers nothing: add `from . import stock`"
    ]


def test_an_import_star_is_caught(tmp_path):
    folder = _package(tmp_path, {"__init__.py": "from .order import *\n", "order.py": ""})

    assert package_problems(folder, "shop.queries") == [
        "shop.queries.__init__ line 1: import *, which hides what each module declares"
    ]


def test_a_package_inside_the_package_is_caught(tmp_path):
    folder = _package(tmp_path, {"__init__.py": "", "reports/__init__.py": "", "reports/csv.py": ""})

    assert package_problems(folder, "shop.queries") == [
        "shop.queries.reports is a package inside the package: make it a module of shop.queries"
    ]


def test_modules_importing_each_other_around_a_loop_are_caught(tmp_path):
    folder = _package(
        tmp_path,
        {
            "__init__.py": "from . import order, stock, supplier\n",
            "order.py": "from .stock import level\n",
            "stock.py": "from shop.queries import supplier\n",
            "supplier.py": "from shop.queries.order import total\n",
        },
    )

    assert package_problems(folder, "shop.queries") == [
        "shop.queries: its modules import each other around a loop: order → stock → supplier → order"
    ]


def test_the_names_read_from_a_package_are_found():
    source = (
        "from shop.queries import order_list, Order\n"
        "from shop import queries as shop_queries\n"
        "import shop.queries\n"
        "shop_queries.stock_level()\n"
        "shop.queries.supplier_of\n"
        "other.queries.not_this_one\n"
    )

    assert names_read(source, "shop.queries") == {"order_list", "Order", "stock_level", "supplier_of"}
    assert names_read("from shop.services import order_place\n", "shop.queries") == set()


def test_the_sweep_takes_the_apps_of_the_saas_and_nothing_else():
    names = {folder.name for folder in app_folders()}

    assert {"accounts", "billing", "hubs", "public"} <= names
    assert names.isdisjoint({"live", "admin", "auth"})


def test_the_sweep_reads_the_saas_s_code_and_not_its_dependencies():
    files = python_files()

    assert {Path("billing/apps.py"), Path("tests/test_door_packages.py")} <= set(files)
    assert not [path for path in files if SKIPPED_DIRS.intersection(path.parts)]


def test_the_sweep_takes_an_admin_split_into_a_package():
    assert REPO / "billing" / "admin" in door_packages()


def test_every_packaged_door_keeps_its_shape():
    problems = [problem for folder in door_packages() for problem in package_problems(folder, dotted(folder))]

    assert problems == []


def test_what_the_code_reads_from_a_packaged_door_is_there():
    sources = [(REPO / path).read_text(encoding="utf-8") for path in python_files()]
    missing = {}
    for folder in door_packages():
        package = dotted(folder)
        module = importlib.import_module(package)
        wanted = set().union(*(names_read(source, package) for source in sources))
        if gone := sorted(name for name in wanted if not hasattr(module, name)):
            missing[package] = gone

    assert missing == {}
