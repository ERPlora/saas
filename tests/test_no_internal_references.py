"""Code is read by people who have never seen the project's planning documents.

Comments, docstrings, test names and log messages have to make sense on their own, so the code never
points at a plan section, a dated planning round, a delivery slice or phase, a task id or a dated plan
or spec. Markdown files are left out: they are where the plans live.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Built from its code point so that this file does not trip its own scan.
SECTION_SIGN = "\N{SECTION SIGN}"

INTERNAL_REFERENCE = re.compile(
    "|".join(
        (
            SECTION_SIGN + r" ?[0-9]",
            r"(Plan|PLAN)(-[A-Z]+)?(\.md)? ?" + SECTION_SIGN,
            r"[Rr](onda|ound) [0-9]{4}-[0-9]{2}",
            r"[Tt]ajada S?[0-9]",
            r"([Pp]hase|[Ff]ase) [0-9]",
            r"(FIX|APP|CLOSE|MIG)-[A-Z0-9]+-[A-Z0-9-]+",
            "MIGRATION" + "-TASK",
            r"BASE-G[0-9]+",
            r"([Pp]lan|[Ss]pec) 20[0-9]{2}-[0-9]{2}",
            r"docs/(plans|superpowers)/",
        )
    )
)

# The end-to-end specs name their screenshots after the task that added them, and renaming those
# string literals would orphan the evidence already captured. There only comments and test titles
# are read.
E2E_DIR = "tests/e2e/"
E2E_SCRIPT_SUFFIXES = {".ts", ".js", ".mjs"}
COMMENT_OR_STRING = re.compile(r"""//.*|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`""")
TEST_TITLE_OPENER = re.compile(r"\b(?:test|it|describe)(?:\.\w+)*\(\s*$")

CODE_SUFFIXES = {
    ".py",
    ".ts",
    ".vue",
    ".js",
    ".mjs",
    ".sh",
    ".css",
    ".html",
    ".toml",
    ".ini",
    ".yml",
    ".yaml",
    ".sql",
}

# Applied migrations are history: they keep the help texts the fields had when they were written.
FROZEN_FILES = {
    "hubs/migrations/0001_initial.py",
    "hubs/migrations/0018_plan_field_names.py",
}

# A clause of Brave Search's terms of use, quoted to the user: an outside contract, not a plan.
QUOTED_CLAUSES = ("Brave Search's terms (" + SECTION_SIGN + "3(b)(i))",)


def code_files():
    """Tracked files plus new ones not ignored, so a reference is caught before its first commit."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout
    paths = sorted({p for p in listing.decode().split("\0") if p})
    return [p for p in paths if Path(p).suffix in CODE_SUFFIXES and (REPO / p).is_file()]


def without_string_literals(line):
    """The line with its string literals emptied, except a test's title; comments stay whole."""
    if line.lstrip().startswith(("//", "/*", "*")):
        return line

    def keep_comment_and_title(match):
        token = match.group(0)
        if token.startswith("//") or TEST_TITLE_OPENER.search(line[: match.start()]):
            return token
        return '""'

    return COMMENT_OR_STRING.sub(keep_comment_and_title, line)


def internal_references(paths, root=REPO):
    found = []
    for path in paths:
        if path in FROZEN_FILES:
            continue
        e2e_script = path.startswith(E2E_DIR) and Path(path).suffix in E2E_SCRIPT_SUFFIXES
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            unquoted = without_string_literals(line) if e2e_script else line
            for clause in QUOTED_CLAUSES:
                unquoted = unquoted.replace(clause, "")
            if INTERNAL_REFERENCE.search(unquoted):
                found.append(f"{path}:{number}: {line.strip()}")
    return found


def test_code_never_points_at_internal_plans():
    paths = code_files()
    assert "tests/test_no_internal_references.py" in paths, "git ls-files listed no code"
    found = internal_references(paths)
    assert not found, "Code that points at internal plans, rounds or slices:\n" + "\n".join(found)


@pytest.mark.parametrize(
    "text",
    [
        "Voice and video calls (Plan " + SECTION_SIGN + "66)",
        "see PLAN-SAAS " + SECTION_SIGN + "47",
        "PLAN.md" + SECTION_SIGN + "5",
        "the limits of " + SECTION_SIGN + "14.2",
        "PLAN-HUB round " + "2026-10-21",
        "ronda " + "2026-11-10f",
        "tajada " + "S3",
        "Tajada " + "4",
        "does not open the public web in phase" + " 1",
        "Phase" + " 2 of the tenancy",
        "en la fase" + " 1",
        "the tabs (FIX" + "-LAUNCH-TABS)",
        "FIX-SAAS" + "-PANEL-UNDER-DASHBOARD-PREFIX",
        "round proposed in APP" + "-HUBS-3",
        "CLOSE" + "-ACCOUNTS-F06",
        "MIG" + "-HUB-12",
        "MIGRATION" + "-TASK",
        "the sparkles of the Hub (BASE" + "-G110)",
        "the taxpayer of an Anexo I, plan" + " 2026-10-15",
        "Plan" + " 2026-10-22, decision 3",
        "spec" + " 2026-10-11",
        "docs" + "/plans/2026-10-31-qa-asistente.md",
        "docs" + "/superpowers/specs/2026-10-10-knowledge.md",
    ],
)
def test_the_scan_catches_each_kind_of_reference(text):
    assert INTERNAL_REFERENCE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "total = round(amount, 2)",
        "Plan the refund before the payment",
        "Section 5 of the AEAT schema",
        "the second round 2 of retries",
        "BASE-F12: a flow of the Hub's WORKBOOK",
        "ACCOUNTS-G93: «Sign out» in the user menu",
        "the subscription schedule's next phase",
        "the plan's price for 2026",
        "docs/api/openapi.json",
    ],
)
def test_the_scan_leaves_ordinary_text_alone(text):
    assert not INTERNAL_REFERENCE.search(text)


def test_an_end_to_end_spec_keeps_its_capture_keys_but_not_its_comments(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "panel" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    lines = (
        "// The flows of the people (@TASK) at three sizes",
        "const KEY = '@FIX';",
        'const atEverySize = captureAtEverySize("@TASK");',
        "await page.screenshot({ path: shot(`@TASK-${key}-${size.width}`) });",
        " * a capture `@TASK-<key>-<size>` stays for the eye",
        "test('@FIX: the panel opens', async ({ page }) => {",
        "test.describe(`@TASK review`, () => {",
        "await go('http://localhost/'); // the @PHASE page",
        "await shot('a'); // it's @FIX, isn't it",
    )
    text = "\n".join(lines).replace("@TASK", "APP" + "-HUBS-3").replace("@FIX", "FIX" + "-SAAS-SOME-KEY")
    spec.write_text(text.replace("@PHASE", "fase" + " 2") + "\n", encoding="utf-8")
    found = internal_references(["tests/e2e/panel/some.spec.ts"], root=tmp_path)
    assert [line.split(":")[1] for line in found] == ["1", "5", "6", "7", "8", "9"]


def test_outside_the_end_to_end_specs_a_string_literal_is_read_too(tmp_path):
    (tmp_path / "accounts").mkdir()
    (tmp_path / "accounts" / "keys.ts").write_text("const KEY = 'FIX" + "-SAAS-SOME-KEY';\n", encoding="utf-8")
    (tmp_path / "tests" / "e2e").mkdir(parents=True)
    (tmp_path / "tests" / "e2e" / "seed.py").write_text('"""The seed (APP' + '-BILLING-2)."""\n', encoding="utf-8")
    found = internal_references(["accounts/keys.ts", "tests/e2e/seed.py"], root=tmp_path)
    assert [line.split(":")[0] for line in found] == ["accounts/keys.ts", "tests/e2e/seed.py"]


def test_a_quoted_clause_of_an_outside_contract_is_not_a_reference(tmp_path):
    (tmp_path / "quote.py").write_text('NOTE = "' + QUOTED_CLAUSES[0] + '"\n', encoding="utf-8")
    (tmp_path / "plan.py").write_text('NOTE = "PLAN ' + SECTION_SIGN + '3"\n', encoding="utf-8")
    assert internal_references(["quote.py", "plan.py"], root=tmp_path) == [
        'plan.py:1: NOTE = "PLAN ' + SECTION_SIGN + '3"'
    ]
