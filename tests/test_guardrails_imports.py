"""Sibling modules never import each other in a circle.

import-linter checks the contract of pyproject.toml's ``[tool.importlinter]`` (``uv run lint-imports``): inside every
package of the SaaS, at any depth, no two children of the same package import each other, directly or round a longer
circle. A child package counts as one with everything inside it, and an import inside a function counts the same as one
at the top of the module. Every top-level package is in the contract, so a new app is checked from its first commit.

The SaaS's apps are platform apps, always on, that declare no requires: unlike the Hub, no contract limits which app
imports which, and an import between two top-level packages is left to the review.

Tests are out of the contract (``**.tests.** -> **``): they may import whatever they check. What broke the contract
when it came in is frozen in its ``ignore_imports``, which import-linter fails as soon as an entry matches no import any
more, and compared with where the branch left origin/main the frozen imports gain no entry between two modules that had
none. An entry may follow its code: when part of a frozen module moves into a submodule of its own
(``billing/queries/__init__.py`` into ``billing/queries/vat.py``), ``billing.vat -> billing.queries`` may become, or come
with, ``billing.vat -> billing.queries.vat``. It is the same dependency between the same two siblings.
"""

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from test_guardrails_size import REPO, git, main_text

CONFIG = "pyproject.toml"
TESTS_OUT = "**.tests.** -> **"
CYCLES_CONTRACT = "no-sibling-cycles"
NO_CONTRACTS_AT_BASE = (
    "pyproject.toml had no import contracts where the branch left origin/main: this is the commit that brings them"
)


def lint_imports(cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    script = Path(sys.executable).with_name("lint-imports")
    return subprocess.run([str(script), "--no-cache"], cwd=cwd, capture_output=True, text=True, check=False)


def importlinter_config(text: str) -> dict | None:
    return tomllib.loads(text).get("tool", {}).get("importlinter")


def current_config() -> dict:
    config = importlinter_config((REPO / CONFIG).read_text(encoding="utf-8"))
    assert config is not None, f"{CONFIG} has no [tool.importlinter] section"
    return config


def top_level_packages(root: Path = REPO) -> list[str]:
    """The folders at the root of the repo with an ``__init__.py`` of their own, new ones included."""
    listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "--", "*/__init__.py")
    assert listed.returncode == 0, listed.stderr
    folders = {Path(path).parent for path in listed.stdout.split()}
    return sorted(str(folder) for folder in folders if len(folder.parts) == 1)


def cycles_contract(packages: list[str]) -> dict:
    return {
        "id": CYCLES_CONTRACT,
        "name": "No sibling modules import each other in a circle",
        "type": "acyclic_siblings",
        "ancestors": packages,
        "ignore_imports": [TESTS_OUT],
    }


def normalized(entry: str) -> str:
    importer, imported = (part.strip() for part in entry.split("->"))
    return f"{importer} -> {imported}"


def frozen(config: dict) -> dict[str, set[str]]:
    """Each contract's frozen imports: its ignore_imports but the one that leaves the tests out."""
    return {
        contract["id"]: {normalized(entry) for entry in contract.get("ignore_imports", [])} - {TESTS_OUT}
        for contract in config.get("contracts", [])
    }


def without_frozen(contract: dict) -> dict:
    return contract | {"ignore_imports": [entry for entry in contract.get("ignore_imports", []) if entry == TESTS_OUT]}


def carried(entry: str, before: set[str]) -> bool:
    """Whether ``entry`` joins the modules of one of ``before``, or submodules of them its code moved into."""

    def within(module: str, frozen_module: str) -> bool:
        return module == frozen_module or module.startswith(f"{frozen_module}.")

    importer, imported = entry.split(" -> ")
    return any(
        within(importer, old_importer) and within(imported, old_imported)
        for old_importer, old_imported in (old.split(" -> ") for old in before)
    )


def gained(now: dict[str, set[str]], before: dict[str, set[str]]) -> list[str]:
    """The frozen imports ``now`` holds that ``before`` did not, leaving out those that followed their code."""
    found = []
    for contract, entries in sorted(now.items()):
        old = before.get(contract, set())
        found += [f"{contract}: {entry}" for entry in sorted(entries - old) if not carried(entry, old)]
    return found


def test_every_import_contract_is_kept():
    result = lint_imports()
    assert result.returncode == 0, (
        "Sibling modules import each other in a circle, or a frozen import of [tool.importlinter] in pyproject.toml "
        "matches no import any more. Break the circle instead of hiding the import inside a function, and remove "
        "the frozen entry the code no longer needs:\n" + result.stdout + result.stderr
    )


def test_every_package_is_in_the_contract_and_nothing_else_is_configured():
    config = current_config()
    packages = top_level_packages()
    assert config["root_packages"] == packages
    # Any other setting, like leaving out the imports under TYPE_CHECKING, would take imports out of the contract.
    assert set(config) == {"root_packages", "contracts"}
    # No depth (every level is checked), no descendants skipped, and a frozen entry that matches no import any more
    # fails, as import-linter does by default.
    assert [without_frozen(contract) for contract in config["contracts"]] == [cycles_contract(packages)]


def test_the_frozen_imports_never_gain_an_entry():
    text = main_text(CONFIG)
    before = importlinter_config(text) if text is not None else None
    if before is None:
        pytest.skip(NO_CONTRACTS_AT_BASE)
    found = gained(frozen(current_config()), frozen(before))
    assert found == [], "The frozen imports only shrink: remove the import instead of freezing it.\n" + "\n".join(found)


def test_the_top_level_packages_are_the_root_folders_with_an_init(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    for path in ("billing/__init__.py", "billing/queries/__init__.py", "hubs/__init__.py", "packages/live/__init__.py"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/checks.py").write_text("", encoding="utf-8")
    assert top_level_packages(tmp_path) == ["billing", "hubs"]


def test_an_entry_new_to_a_contract_is_gained_and_the_tests_exemption_never_is():
    before = {"cycles": {"billing.a -> billing.b"}}
    now = {"cycles": {"billing.a -> billing.b", "billing.c -> billing.d"}, "other": set()}
    assert gained(now, before) == ["cycles: billing.c -> billing.d"]
    config = {"contracts": [{"id": "other", "ignore_imports": [TESTS_OUT, "hubs.api ->  hubs.queries"]}]}
    assert frozen(config) == {"other": {"hubs.api -> hubs.queries"}}


def test_a_frozen_import_follows_its_code_into_the_submodules_of_its_modules():
    before = {"cycles": {"billing.vat -> billing.queries", "accounts.models -> accounts.services"}}
    now = {
        "cycles": {
            "billing.vat -> billing.queries",
            "billing.vat -> billing.queries.vat",
            "accounts.models -> accounts.services.account_businesses",
        }
    }
    assert gained(now, before) == []


def test_another_module_a_longer_name_or_the_package_above_carries_nothing():
    before = {"cycles": {"assistant.attachments -> assistant.turn"}}
    now = {
        "cycles": {
            "assistant.media -> assistant.turn",
            "assistant.attachments -> assistant.turns",
            "assistant.attachments -> assistant",
        }
    }
    assert gained(now, before) == [
        "cycles: assistant.attachments -> assistant",
        "cycles: assistant.attachments -> assistant.turns",
        "cycles: assistant.media -> assistant.turn",
    ]


def write_tree(root: Path, files: dict[str, str]) -> None:
    for path, source in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(source, encoding="utf-8")


def toml_config(root_packages: list[str], contracts: list[dict]) -> str:
    lines = ["[tool.importlinter]", f"root_packages = {json.dumps(root_packages)}"]
    for contract in contracts:
        lines += ["", "[[tool.importlinter.contracts]]"]
        lines += [f"{key} = {json.dumps(value)}" for key, value in contract.items()]
    return "\n".join(lines) + "\n"


def test_the_contract_catches_a_circle_at_any_depth_even_hidden_in_a_function_but_not_in_tests(tmp_path):
    """The contract in the shape this test asks of pyproject.toml, on a small tree: a circle between two modules of
    a package's subpackage, one of its imports inside a function, and tests that import whatever they check."""
    packages = ["billing/__init__.py", "billing/queries/__init__.py", "billing/tests/__init__.py", "hubs/__init__.py"]
    write_tree(tmp_path, dict.fromkeys(packages, ""))
    write_tree(
        tmp_path,
        {
            "billing/queries/plans.py": "from billing.queries import prices\n",
            "billing/queries/prices.py": "def later():\n    from billing.queries import plans\n",
            "billing/vat.py": "from billing import queries\n",
            "billing/tests/test_vat.py": "from billing import vat\nfrom billing.tests import test_plans\n",
            "billing/tests/test_plans.py": "from billing.tests import test_vat\n",
            "hubs/models.py": "from billing import vat\n",
        },
    )
    (tmp_path / CONFIG).write_text(toml_config(["billing", "hubs"], [cycles_contract(["billing", "hubs"])]))
    report = lint_imports(cwd=tmp_path).stdout
    assert "No cycles are allowed in billing.queries." in report
    assert "billing.tests" not in report
    assert "Contracts: 0 kept, 1 broken." in report
