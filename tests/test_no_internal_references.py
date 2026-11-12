"""Code is read by people who have never seen the project's planning documents.

Comments, docstrings, test names and log messages have to make sense on their own, so the code never
points at a plan section, a dated planning round or a delivery slice. Markdown files are left out:
they are where the plans live.
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
        )
    )
)

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


def internal_references(paths, root=REPO):
    found = []
    for path in paths:
        if path in FROZEN_FILES:
            continue
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            unquoted = line
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
    ],
)
def test_the_scan_leaves_ordinary_text_alone(text):
    assert not INTERNAL_REFERENCE.search(text)


def test_a_quoted_clause_of_an_outside_contract_is_not_a_reference(tmp_path):
    (tmp_path / "quote.py").write_text('NOTE = "' + QUOTED_CLAUSES[0] + '"\n', encoding="utf-8")
    (tmp_path / "plan.py").write_text('NOTE = "PLAN ' + SECTION_SIGN + '3"\n', encoding="utf-8")
    assert internal_references(["quote.py", "plan.py"], root=tmp_path) == [
        'plan.py:1: NOTE = "PLAN ' + SECTION_SIGN + '3"'
    ]
