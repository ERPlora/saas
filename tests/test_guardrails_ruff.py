"""Python code stays clear of the mistakes ruff finds, besides the function limits.

Next to the limits tests/test_guardrails_lint.py describes, ruff checks the rule families E4, E7 and E9 (imports out of
place, statements that read wrong, code that cannot be read), F (an import or a variable left unused, a name never
defined, a key written twice), B (a closure that reads a loop variable late, a zip that silently drops what is left
over) and DJ (a nullable text field, a form that takes every field of its model). That test runs ruff over the code;
this one pins its configuration down.

What broke one of these rules when it came in is frozen in pyproject.toml's ``[tool.ruff.lint.per-file-ignores]``, one
entry per file with the rules it breaks. An entry that no longer silences anything fails here. Compared with where the
branch left origin/main, the entries gain no file-and-rule pair and no frozen rule is broken more often, counted per
rule wherever its code moved: the list only shrinks. An entry may follow its code into the package of the same name
(``whatsapp/services.py`` into ``whatsapp/services/__init__.py`` or ``whatsapp/services/messages.py``) or into flat
siblings named after it (``test_demo.py`` into ``test_demo_seed.py``). The ``noqa`` markers that name one of these
rules, and those that name none and so silence them all, only shrink too, per rule, wherever they moved.

In tests a fixture comes back as an argument under the name it was imported with, so redefining a name (F811) is not
checked there, like the argument limits.
"""

import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections import Counter
from pathlib import Path

import pytest
from test_guardrails_lint import git_grep, reported, widened
from test_guardrails_size import REPO, git, main_base, main_text

CONFIG = "pyproject.toml"
PRODUCTION = "billing/probe.py"
TEST = "billing/tests/test_probe.py"
FAMILIES = ("B", "DJ", "E4", "E7", "E9", "F")
LIMITS = ("C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0917")
# One whole rule of the families: F401 or E402, never a family alone, nor BLE001 or E501.
FAMILY_RULE = re.compile(f"({'|'.join(FAMILIES)})[0-9]+")
TEST_GLOBS = ("**/tests/**", "**/e2e/**", "**/test_*.py", "**/conftest.py")
TEST_EXEMPTIONS = ["F811", "PLR0913", "PLR0917"]
GLOB = re.compile(r"[*?\[\]{}!]")
PYTHON = ("*.py", ":(exclude)*/migrations/*")
# A file-wide prefix, ``ruff:`` or ``flake8:``, in any case, as ruff reads it.
FILE_WIDE = r"([Rr][Uu][Ff][Ff]|[Ff][Ll][Aa][Kk][Ee]8)[[:space:]]*:[[:space:]]*"
# A noqa anywhere on its line, file-wide or not, with codes or without; ruff reads noqa in any case.
NOQA_MARKERS = rf"#[[:space:]]*({FILE_WIDE})?[Nn][Oo][Qq][Aa][^#]*"
# A range suppression, `# ruff: disable[<codes>]` alone on its line, which silences its codes down to the matching
# `# ruff: enable[…]`.
RANGE_MARKER = r"^[[:space:]]*#[[:space:]]*[Rr][Uu][Ff][Ff][[:space:]]*:[[:space:]]*[Dd][Ii][Ss][Aa][Bb][Ll][Ee][[:space:]]*\[[^]]*\]"
# Written in two pieces so that this file adds no marker of its own to the count.
NOQA = "#" + " noqa"
FILE_NOQA = NOQA.replace("# ", "# ruff: ")
EVERY_RULE = "every rule"
NO_RULES_AT_BASE = (
    "ruff did not check these rules where the branch left origin/main: this is the commit that brings them and freezes "
    "what breaks them today"
)

RUFF_CONFIGURATION = {
    "extend-exclude": ["packages", "migrations"],
    "force-exclude": True,
    "format": {"exclude": ["*"]},
    "lint": {
        "select": sorted([*FAMILIES, *LIMITS, "RUF100"]),
        "external": ["A002", "BLE001", "E402", "F811", "PT011", "S308"],
        "mccabe": {"max-complexity": 10},
        "pylint": {"max-args": 5, "max-positional-args": 5, "max-branches": 12, "max-returns": 6, "max-statements": 50},
        "per-file-ignores": dict.fromkeys(TEST_GLOBS, TEST_EXEMPTIONS),
    },
}

FORM = """from django import forms

from hubs.models import Hub


class HubForm(forms.ModelForm):
    class Meta:
        model = Hub
        fields = "__all__"
"""


def ruff_config(text: str) -> dict:
    return tomllib.loads(text).get("tool", {}).get("ruff", {})


def current_config() -> dict:
    return ruff_config((REPO / CONFIG).read_text(encoding="utf-8"))


def frozen(config: dict) -> dict[str, list[str]]:
    """The per-file-ignores entries that name one file: what broke a rule there when it came in."""
    ignores = config.get("lint", {}).get("per-file-ignores", {})
    return {path: rules for path, rules in ignores.items() if not GLOB.search(path)}


def without_frozen(config: dict) -> dict:
    """The configuration with only the per-file-ignores that apply to a kind of file, never to one file."""
    lint = config.get("lint", {})
    ignores = {path: rules for path, rules in lint.get("per-file-ignores", {}).items() if GLOB.search(path)}
    return config | {"lint": lint | {"per-file-ignores": ignores}}


def pairs(entries: dict[str, list[str]]) -> set[tuple[str, str]]:
    return {(path, rule) for path, rules in entries.items() for rule in rules}


def python_files() -> set[str]:
    listed = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.py")
    assert listed.returncode == 0, listed.stderr
    return set(listed.stdout.split())


def entry_problems(entries: dict[str, list[str]], files: set[str]) -> list[str]:
    """What is wrong with each frozen entry: a path that is not a Python file of the repo, or a rule that is not one
    whole rule of the families."""
    problems = []
    for path, rules in sorted(entries.items()):
        if "/" not in path:
            problems.append(f"{path}: ruff reads a name without a folder as every file of that name; fix the file")
        elif path not in files:
            problems.append(f"{path}: no such Python file; move the entry with its code, or remove it")
        wrong = [rule for rule in rules if not FAMILY_RULE.fullmatch(rule)]
        problems += [f"{path}: {rule} is not one rule of {', '.join(FAMILIES)}" for rule in wrong]
    return problems


def inline_table(table: dict[str, list[str]]) -> str:
    return "{" + ", ".join(f"{json.dumps(key)} = {json.dumps(value)}" for key, value in table.items()) + "}"


def found_without_the_entries(entries: dict[str, list[str]], root: Path = REPO) -> Counter[tuple[str, str]]:
    """How often ruff finds each file-and-rule pair in the frozen files under ``root`` once their entries are lifted,
    with the branch's configuration."""
    if not entries:
        return Counter()
    kept = without_frozen(current_config())["lint"]["per-file-ignores"]
    lifted = f"lint.per-file-ignores = {inline_table(kept)}"
    command = [sys.executable, "-m", "ruff", "check", "--no-cache", "--output-format", "json", "--config", lifted]
    result = subprocess.run([*command, *entries], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode in (0, 1), result.stderr
    findings = json.loads(result.stdout)
    return Counter((Path(found["filename"]).relative_to(root).as_posix(), found["code"]) for found in findings)


def found_at_base(entries: dict[str, list[str]]) -> Counter[tuple[str, str]]:
    """The same for the frozen files as they were where the branch left origin/main, copied out of git with this
    configuration."""
    if not entries:
        return Counter()
    archive = subprocess.run(
        ["git", "archive", "--format=tar", main_base(), "--", *entries], cwd=REPO, capture_output=True, check=False
    )
    assert archive.returncode == 0, archive.stderr.decode()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder).resolve()
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(root, filter="data")
        shutil.copyfile(REPO / CONFIG, root / CONFIG)
        return found_without_the_entries(entries, root)


def unneeded(entries: dict[str, list[str]], found: Counter[tuple[str, str]]) -> list[str]:
    return [f"{path}: {rule}" for path, rule in sorted(pairs(entries) - found.keys())]


def frozen_counts(entries: dict[str, list[str]], found: Counter[tuple[str, str]]) -> Counter[str]:
    """How often each frozen rule is broken in the files frozen for it."""
    frozen_pairs = pairs(entries)
    counts: Counter[str] = Counter()
    for (path, rule), times in found.items():
        if (path, rule) in frozen_pairs:
            counts[rule] += times
    return counts


def module_of(path: str) -> str:
    return path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def follows(path: str, old: str) -> bool:
    """Whether ``path`` may hold code ``old`` held: the same module, one inside its package, or a flat sibling named
    after it."""
    module, before = module_of(path), module_of(old)
    return module == before or module.startswith((f"{before}.", f"{before}_"))


def gained(now: dict[str, list[str]], before: dict[str, list[str]]) -> list[str]:
    """The frozen pairs ``now`` holds that ``before`` did not, leaving out those that followed their code."""
    old = pairs(before)
    return [
        f"{path}: {rule}"
        for path, rule in sorted(pairs(now) - old)
        if not any(rule == old_rule and follows(path, old_path) for old_path, old_rule in old)
    ]


def after_noqa(marker: str) -> str:
    return re.split("noqa", marker, flags=re.IGNORECASE)[-1].lstrip()


def family_codes(markers: list[str]) -> Counter[str]:
    """The rules of the families each noqa or range marker names. A noqa that names no rule silences them all, on its
    line or in its whole file."""
    codes = [code for marker in markers for code in re.findall(r"[A-Z]+[0-9]+", marker)]
    bare = [marker for marker in markers if "noqa" in marker.lower() and not after_noqa(marker).startswith(":")]
    return Counter(code for code in codes if FAMILY_RULE.fullmatch(code)) + Counter({EVERY_RULE: len(bare)})


def markers(*commit: str) -> list[str]:
    """Every noqa and range marker of the Python files in ``commit``, or in the working tree, new files included."""
    options = () if commit else ("--untracked",)
    found = []
    for pattern in (NOQA_MARKERS, RANGE_MARKER):
        found += git_grep(REPO, *options, "-o", "-E", "-e", pattern, *commit, "--", *PYTHON)
    return found


def frozen_before() -> dict:
    """The ruff configuration where the branch left origin/main, skipping while it did not check these rules yet."""
    before = ruff_config(main_text(CONFIG) or "")
    if not set(FAMILIES) <= set(before.get("lint", {}).get("select", [])):
        pytest.skip(NO_RULES_AT_BASE)
    return before


@pytest.mark.parametrize(
    ("code", "rule"),
    [
        ("import os\n", "F401"),
        ("first = 1; second = 2\n", "E702"),
        ("double = lambda value: value * 2\n", "E731"),
        ("def paired(a, b):\n    return list(zip(a, b))\n", "B905"),
        (FORM, "DJ007"),
    ],
    ids=["F401", "E702", "E731", "B905", "DJ007"],
)
def test_each_family_finds_its_mistake(code, rule):
    assert reported(code, PRODUCTION) == {rule}


def test_redefining_a_name_counts_in_production_but_not_in_tests():
    twice = "def shop():\n    return 1\n\n\ndef shop():\n    return 2\n"
    assert reported(twice, PRODUCTION) == {"F811"}
    assert reported(twice, TEST) == set()
    assert reported(twice, "billing/conftest.py") == set()


def test_layout_and_style_are_still_not_checked():
    code = f"import sys\nimport os\nvalue=1\nLONG = '{'a' * 120}'  \nprint(os, sys, value, LONG)\n"
    assert reported(code, PRODUCTION) == set()


def test_the_ruff_configuration_is_exactly_the_rules_and_the_limits():
    """Excluding a folder, ignoring a rule everywhere or loosening a value would switch a check off for good: any change
    to the configuration shows here first, and no other file configures ruff. The entries of one file are the frozen
    ones, which the tests below keep shrinking."""
    assert without_frozen(current_config()) == RUFF_CONFIGURATION
    configs = git(REPO, "ls-files", "--cached", "--others", "--exclude-standard", "--", "*ruff.toml", "*pyproject.toml")
    assert configs.stdout.split() == [CONFIG]


def test_no_rule_leaves_the_selection():
    before = ruff_config(main_text(CONFIG) or "").get("lint", {}).get("select", [])
    assert sorted(set(before) - set(current_config()["lint"]["select"])) == []


def test_each_frozen_entry_names_a_file_and_whole_rules():
    assert entry_problems(frozen(current_config()), python_files()) == []


def test_each_frozen_entry_still_silences_something():
    entries = frozen(current_config())
    found = unneeded(entries, found_without_the_entries(entries))
    assert found == [], f"Frozen rules a file no longer breaks: remove them from {CONFIG}.\n" + "\n".join(found)


def test_the_frozen_entries_never_gain_one():
    found = gained(frozen(current_config()), frozen(frozen_before()))
    assert found == [], "The frozen rules only shrink: fix the code instead of freezing it.\n" + "\n".join(found)


def test_the_frozen_files_never_break_their_rules_more_often():
    now_entries, base_entries = frozen(current_config()), frozen(frozen_before())
    now = frozen_counts(now_entries, found_without_the_entries(now_entries))
    found = widened(now, frozen_counts(base_entries, found_at_base(base_entries)))
    assert found == [], "A frozen file breaks its rule once more: fix the code instead.\n" + "\n".join(found)


def test_the_noqa_markers_of_these_rules_never_grow():
    found = widened(family_codes(markers()), family_codes(markers(main_base())))
    assert found == [], "A new noqa for these rules, or one that names none: fix the code instead.\n" + "\n".join(found)


def test_a_rule_is_one_whole_rule_of_the_families():
    rules, others = ("F401", "E402", "E902", "B905", "DJ001"), ("F", "E4", "BLE001", "E501", "C901", "RUF100", "f401")
    assert [code for code in rules if not FAMILY_RULE.fullmatch(code)] == []
    assert [code for code in others if FAMILY_RULE.fullmatch(code)] == []


def test_a_frozen_entry_names_one_python_file_and_whole_rules():
    entries = {
        "billing/vat.py": ["F401"],
        "conftest.py": ["F401"],
        "billing/gone.py": ["E731"],
        "hubs/admin.py": ["F", "BLE001", "C901", "RUF100"],
    }
    assert entry_problems(entries, {"billing/vat.py", "hubs/admin.py", "conftest.py"}) == [
        "billing/gone.py: no such Python file; move the entry with its code, or remove it",
        "conftest.py: ruff reads a name without a folder as every file of that name; fix the file",
        "hubs/admin.py: F is not one rule of B, DJ, E4, E7, E9, F",
        "hubs/admin.py: BLE001 is not one rule of B, DJ, E4, E7, E9, F",
        "hubs/admin.py: C901 is not one rule of B, DJ, E4, E7, E9, F",
        "hubs/admin.py: RUF100 is not one rule of B, DJ, E4, E7, E9, F",
    ]


def test_an_entry_ruff_no_longer_needs_is_reported():
    entries = {"billing/vat.py": ["F401"], "hubs/admin.py": ["B905", "DJ007"]}
    found = Counter({("billing/vat.py", "F401"): 12, ("hubs/admin.py", "DJ007"): 1, ("hubs/models.py", "F401"): 2})
    assert unneeded(entries, found) == ["hubs/admin.py: B905"]


def test_only_the_entries_of_one_file_are_frozen():
    config = {"lint": {"select": ["F"], "per-file-ignores": {"**/tests/**": ["F811"], "hubs/admin.py": ["F401"]}}}
    assert frozen(config) == {"hubs/admin.py": ["F401"]}
    assert without_frozen(config) == {"lint": {"select": ["F"], "per-file-ignores": {"**/tests/**": ["F811"]}}}


def test_a_pair_new_to_the_list_is_gained_and_one_that_follows_its_code_is_not():
    before = {"whatsapp/services.py": ["F401"], "public/tests/test_demo.py": ["B007"]}
    now = {
        "whatsapp/services/__init__.py": ["F401"],
        "whatsapp/services/messages.py": ["F401"],
        "public/tests/test_demo_seed.py": ["B007"],
        "whatsapp/services.py": ["B905", "F401"],
        "whatsapp/queries.py": ["F401"],
        "public/tests/test_demos.py": ["B007"],
        "public/tests/test_dem.py": ["B007"],
        "whatsapp/__init__.py": ["F401"],
    }
    assert gained(now, before) == [
        "public/tests/test_dem.py: B007",
        "public/tests/test_demos.py: B007",
        "whatsapp/__init__.py: F401",
        "whatsapp/queries.py: F401",
        "whatsapp/services.py: B905",
    ]


def test_the_noqa_markers_count_only_the_rules_of_the_families():
    found = [
        f"import os  {NOQA}: F401",
        f"{NOQA}: E402, F403 - star import of the settings",
        f"def a():  {NOQA}: C901",
        f"x = 1  {NOQA}: BLE001",
        "# ruff: disable[B905]",
        f"{FILE_NOQA}: B905",
    ]
    assert family_codes(found) == Counter({"F401": 1, "E402": 1, "F403": 1, "B905": 2})


def test_a_noqa_that_names_no_rule_counts_as_silencing_every_rule():
    bare = [f"import os  {NOQA}", f"x = 1  {NOQA} - on purpose", FILE_NOQA]
    found = [*bare, f"y = 2  {NOQA}: F401", "# ruff: disable[B905]"]
    assert family_codes(found) == Counter({EVERY_RULE: 3, "F401": 1, "B905": 1})


@pytest.mark.parametrize(
    "line",
    [f"import os  {NOQA}", f"import os  {NOQA} - on purpose", f"import os  {NOQA}: F401", f"{FILE_NOQA}: B905"],
    ids=["bare", "bare with a reason", "one rule", "file-wide rule"],
)
def test_every_noqa_that_can_silence_these_rules_is_found(line):
    command = ["grep", "-o", "-E", NOQA_MARKERS]
    found = subprocess.run(command, input=f"{line}\n", capture_output=True, text=True, check=False)
    assert found.stdout.splitlines() == [line[line.index("#") :]]


def test_a_frozen_rule_counts_only_in_the_files_frozen_for_it():
    entries = {"billing/vat.py": ["F401"], "hubs/admin.py": ["B905"]}
    found = Counter({("billing/vat.py", "F401"): 2, ("hubs/admin.py", "B905"): 1, ("hubs/admin.py", "F401"): 4})
    assert frozen_counts(entries, found) == Counter({"F401": 2, "B905": 1})
