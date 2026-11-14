"""Python functions stay within the limits a person can still follow, checked by ruff from the suite.

Complexity at most 10 (C901), at most 50 statements (PLR0915), 12 branches (PLR0912), 6 returns (PLR0911) and
5 arguments (PLR0913, PLR0917). Tests may take more arguments: pytest's fixtures arrive as arguments. A function
over a limit today carries a ``# noqa`` for it, and RUF100 fails on a ``# noqa`` that no longer silences
anything, so those exceptions only go away. Neither those ``# noqa`` nor the TypeScript ones in
``eslint-suppressions.json`` may grow in number against ``origin/main``.
"""

import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import pytest
from test_guardrails_size import MAIN, commit_as_main, git_repo, main_text

REPO = Path(__file__).resolve().parent.parent
FUNCTION_LIMITS = {"C901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0917"}
ARGUMENT_LIMITS = {"PLR0913", "PLR0917"}
SUPPRESSIONS = "eslint-suppressions.json"

# Ten independent ifs: complexity 11, and no other limit crossed.
TOO_COMPLEX = (
    "def label(value):\n    text = ''\n"
    + "".join(f"    if value & {1 << bit}:\n        text += '{bit}'\n" for bit in range(10))
    + "    return text\n"
)
SIX_ARGUMENTS = "def make(a, b, c, d, e, f):\n    return a\n"


def ruff(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--no-cache",
            "--output-format",
            "concise",
            *args,
        ],
        cwd=REPO,
        input=stdin,
        capture_output=True,
        text=True,
    )


def reported(code: str, path: str) -> set[str]:
    """The rule codes ruff reports on ``code`` as if it were the file at ``path``."""
    output = ruff("--stdin-filename", path, "-", stdin=code).stdout
    return {line.split(": ", 1)[1].split()[0] for line in output.splitlines() if line.startswith(path)}


def silenced_limits(lines: Iterable[str]) -> Counter:
    """How many times each function limit is silenced by a ``# noqa`` in ``lines``."""
    counts = Counter()
    for line in lines:
        for directive in re.findall(r"#\s*noqa:([^#]*)", line):
            counts.update(code for code in re.findall(r"\b[A-Z]+[0-9]+\b", directive) if code in FUNCTION_LIMITS)
    return counts


def suppressed_limits(text: str) -> Counter:
    """How many violations of each rule ``eslint-suppressions.json`` suppresses, over all its files."""
    counts = Counter()
    for rules in json.loads(text).values():
        counts.update({rule: entry["count"] for rule, entry in rules.items()})
    return counts


def widened(counts: Counter, main_counts: Counter) -> list[str]:
    return [
        f"{rule}: {counts[rule]}, {main_counts[rule]} on {MAIN}"
        for rule in sorted(counts)
        if counts[rule] > main_counts[rule]
    ]


def git_grep(root: Path, *args: str) -> list[str]:
    result = subprocess.run(["git", "grep", "-h", "-I", *args], cwd=root, capture_output=True, text=True)
    assert result.returncode in (0, 1), result.stderr
    return result.stdout.splitlines()


def silenced_more_than_main(root: Path = REPO) -> list[str] | None:
    """The limits silenced more often than on main, counted over the whole repository so that moving a function
    to another file is no new exception; None while main has no function limits (the change that brings them in).
    """
    main_pyproject = main_text("pyproject.toml", root)
    if main_pyproject is None or "lint" not in tomllib.loads(main_pyproject).get("tool", {}).get("ruff", {}):
        return None
    counts = silenced_limits(git_grep(root, "--untracked", "-e", "noqa", "--", "*.py"))
    return widened(counts, silenced_limits(git_grep(root, "-e", "noqa", MAIN, "--", "*.py")))


def suppressed_more_than_main(root: Path = REPO) -> list[str] | None:
    """The same for ``eslint-suppressions.json``; None while main has none."""
    main_suppressions = main_text(SUPPRESSIONS, root)
    if main_suppressions is None:
        return None
    return widened(suppressed_limits((root / SUPPRESSIONS).read_text()), suppressed_limits(main_suppressions))


def test_no_function_limit_is_silenced_more_often_than_on_main():
    problems = silenced_more_than_main()
    assert not problems, "Split the function instead of silencing a limit:\n" + "\n".join(problems or [])


def test_no_eslint_limit_is_suppressed_more_often_than_on_main():
    problems = suppressed_more_than_main()
    assert not problems, "Split the function instead of suppressing a limit:\n" + "\n".join(problems or [])


def test_no_python_function_goes_over_a_limit():
    result = ruff()
    assert result.returncode == 0, result.stdout + result.stderr


def test_ruff_checks_only_the_function_limits_with_the_rule_values():
    lint = tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]
    assert set(lint["select"]) == FUNCTION_LIMITS | {"RUF100"}
    assert lint["mccabe"] == {"max-complexity": 10}
    assert lint["pylint"] == {
        "max-args": 5,
        "max-positional-args": 5,
        "max-branches": 12,
        "max-returns": 6,
        "max-statements": 50,
    }


def test_migrations_are_left_out():
    assert "migrations" in tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["ruff"]["extend-exclude"]


def test_ruff_never_reformats_the_code():
    """The code is written about 120 columns wide: ruff's formatter would rewrite whole files, even one named."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "billing/services.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_function_too_complex_is_reported():
    assert reported(TOO_COMPLEX, "billing/sample.py") == {"C901"}


def test_a_production_function_with_six_arguments_is_reported():
    assert reported(SIX_ARGUMENTS, "billing/sample.py") == ARGUMENT_LIMITS


@pytest.mark.parametrize("path", ["billing/tests/test_sample.py", "billing/tests/helpers.py", "conftest.py"])
def test_tests_may_take_more_arguments_but_not_more_complexity(path):
    assert reported(SIX_ARGUMENTS, path) == set()
    assert reported(TOO_COMPLEX, path) == {"C901"}


def test_a_noqa_that_silences_nothing_is_reported():
    assert reported("value = 1  # noqa: C901\n", "billing/sample.py") == {"RUF100"}


def test_a_noqa_kept_for_another_linter_is_left_alone():
    assert (
        reported(
            "import os  # noqa: F401 - imported for its side effect\n",
            "billing/sample.py",
        )
        == set()
    )


def test_the_silenced_limits_are_counted_per_rule():
    lines = [
        "def a(x):  # noqa: C901, PLR0911 - one grammar",
        "def b(x):  # noqa: C901",
        "import os  # noqa: F401",
        "value = 1  # a comment that mentions C901",
    ]
    assert silenced_limits(lines) == Counter({"C901": 2, "PLR0911": 1})


def test_the_eslint_suppressions_are_counted_per_rule():
    text = '{"a.vue": {"complexity": {"count": 2}}, "b.ts": {"complexity": {"count": 1}, "max-params": {"count": 1}}}'
    assert suppressed_limits(text) == Counter({"complexity": 3, "max-params": 1})


def test_an_exception_more_than_on_main_is_reported():
    counts = Counter({"C901": 3, "PLR0911": 2, "PLR0913": 1})
    main_counts = Counter({"C901": 3, "PLR0911": 1, "PLR0915": 4})
    assert widened(counts, main_counts) == ["PLR0911: 2, 1 on origin/main", "PLR0913: 1, 0 on origin/main"]


LIMITS_ON = '[tool.ruff.lint]\nselect = ["C901"]\n'


def test_a_new_noqa_against_main_is_reported(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"pyproject.toml": LIMITS_ON, "a.py": "def a(x):  # noqa: C901\n    return x\n"})
    (tmp_path / "b.py").write_text("def b(x):  # noqa: C901, PLR0911\n    return x\n")
    assert silenced_more_than_main(tmp_path) == ["C901: 2, 1 on origin/main", "PLR0911: 1, 0 on origin/main"]


def test_a_noqa_moved_to_another_file_is_no_new_exception(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"pyproject.toml": LIMITS_ON, "a.py": "def a(x):  # noqa: C901\n    return x\n"})
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("def a(x):  # noqa: C901\n    return x\n")
    assert silenced_more_than_main(tmp_path) == []


def test_before_main_has_function_limits_there_is_nothing_to_compare(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"pyproject.toml": "[project]\nname = 'saas'\n", "a.py": "x = 1\n"})
    (tmp_path / "b.py").write_text("def b(x):  # noqa: C901\n    return x\n")
    assert silenced_more_than_main(tmp_path) is None


def test_a_new_eslint_suppression_against_main_is_reported(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {SUPPRESSIONS: '{"a.vue": {"complexity": {"count": 1}}}'})
    (tmp_path / SUPPRESSIONS).write_text(
        '{"a.vue": {"complexity": {"count": 1}}, "b.ts": {"complexity": {"count": 1}}}'
    )
    assert suppressed_more_than_main(tmp_path) == ["complexity: 2, 1 on origin/main"]
    (tmp_path / SUPPRESSIONS).write_text("{}")
    assert suppressed_more_than_main(tmp_path) == []
