"""No code file grows past the size a person can still keep in their head.

A production file stops at 1,000 physical lines and a test file at 1,500. Generated and third-party files do not
count. The files over their cap are listed in ``.file-size-allow``, one per line as ``<ceiling> <path> <issue>``,
and that list only shrinks: a listed file never grows past its ceiling, its ceiling follows it down as it shrinks,
it leaves the list once it fits its cap, and compared with the list on ``origin/main`` the list gains no path and
raises no ceiling.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ALLOW_LIST = ".file-size-allow"
MAIN = "origin/main"

PRODUCTION_CAP = 1000
TEST_CAP = 1500
# A ceiling is the file's size rounded up to the next hundred.
CEILING_STEP = 100

CODE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".vue", ".sh", ".css", ".html"})
# Nobody writes these by hand: Django migrations, installed packages, build output and third-party bundles.
GENERATED_DIRS = frozenset({"migrations", "node_modules", "dist"})
GENERATED_PREFIXES = ("static/vendor/",)
TEST_DIRS = frozenset({"tests", "__tests__", "e2e"})
TEST_NAME = re.compile(r"test_.*\.py|conftest\.py|.*\.(test|spec)\.[^.]+")
ENTRY = re.compile(r"(?P<ceiling>[0-9]+) (?P<path>\S+) (?P<issue>saas#[0-9]+)")


def physical_lines(data: bytes) -> int:
    """The lines as an editor numbers them: a last line without its newline still counts."""
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def is_generated(path: str) -> bool:
    return bool(GENERATED_DIRS.intersection(path.split("/")[:-1])) or path.startswith(GENERATED_PREFIXES)


def is_test(path: str) -> bool:
    folders, name = path.split("/")[:-1], path.rsplit("/", 1)[-1]
    return bool(TEST_DIRS.intersection(folders)) or TEST_NAME.fullmatch(name) is not None


def cap_of(path: str) -> int:
    return TEST_CAP if is_test(path) else PRODUCTION_CAP


def rounded_ceiling(lines: int) -> int:
    return -(-lines // CEILING_STEP) * CEILING_STEP


def code_sizes(root: Path = REPO) -> dict[str, int]:
    """Lines of every code file git tracks or would track (new files count before they are added)."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode()
    paths = {path for path in listing.split("\0") if Path(path).suffix in CODE_SUFFIXES and not is_generated(path)}
    return {path: physical_lines((root / path).read_bytes()) for path in sorted(paths) if (root / path).is_file()}


def parse_allow_list(text: str) -> dict[str, int]:
    """The list's entries as path → ceiling. Blank lines and lines starting with ``#`` are notes."""
    ceilings = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        entry = ENTRY.fullmatch(line)
        if entry is None:
            raise ValueError(f"{ALLOW_LIST} line {number}: {line!r} is not '<ceiling> <path> saas#<issue>'")
        if entry["path"] in ceilings:
            raise ValueError(f"{ALLOW_LIST} line {number}: {entry['path']} is listed twice")
        ceilings[entry["path"]] = int(entry["ceiling"])
    return ceilings


def read_allow_list(root: Path = REPO) -> dict[str, int]:
    """The list in the working tree; without one, every file has to fit its cap."""
    allow_list = root / ALLOW_LIST
    return parse_allow_list(allow_list.read_text()) if allow_list.exists() else {}


def main_text(name: str, root: Path = REPO) -> str | None:
    """The file ``name`` as it is on ``origin/main``, or None when main does not have it.

    Without ``origin/main`` the exceptions cannot be compared with main's, and that fails instead of passing
    quietly: the workflow that runs the suite fetches main, and a local tree only needs ``git fetch origin main``.
    """

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)

    if git("rev-parse", "--verify", "--quiet", f"{MAIN}^{{commit}}").returncode != 0:
        pytest.fail(f"{MAIN} is not in this clone, so {name} cannot be compared with main's: git fetch origin main")
    if git("cat-file", "-e", f"{MAIN}:{name}").returncode != 0:
        return None
    shown = git("show", f"{MAIN}:{name}")
    assert shown.returncode == 0, shown.stderr
    return shown.stdout


def main_allow_list(root: Path = REPO) -> dict[str, int] | None:
    """The list on ``origin/main``, or None while main has none yet (the change that brings the list in)."""
    text = main_text(ALLOW_LIST, root)
    return None if text is None else parse_allow_list(text)


def unlisted_over_cap(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    return [
        f"{path}: {lines} lines, over its cap of {cap_of(path)}"
        for path, lines in sizes.items()
        if path not in ceilings and lines > cap_of(path)
    ]


def over_ceiling(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    return [
        f"{path}: {sizes[path]} lines, over its ceiling of {ceiling}"
        for path, ceiling in ceilings.items()
        if path in sizes and sizes[path] > ceiling
    ]


def stale_entries(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Entries to take out of the list: the file is gone, is not measured, or already fits its cap."""
    stale = []
    for path in ceilings:
        if path not in sizes:
            stale.append(f"{path}: no code file of this repository is measured at this path")
        elif sizes[path] <= cap_of(path):
            stale.append(f"{path}: {sizes[path]} lines, it fits its cap of {cap_of(path)}")
    return stale


def loose_ceilings(sizes: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Ceilings left above a file that shrank: they come down to its size rounded up to the hundred."""
    return [
        f"{path}: {sizes[path]} lines, lower its ceiling from {ceiling} to {rounded_ceiling(sizes[path])}"
        for path, ceiling in ceilings.items()
        if path in sizes and ceiling > rounded_ceiling(sizes[path])
    ]


def widened_entries(ceilings: dict[str, int], main_ceilings: dict[str, int]) -> list[str]:
    widened = []
    for path, ceiling in ceilings.items():
        if path not in main_ceilings:
            widened.append(f"{path}: not listed on {MAIN}")
        elif ceiling > main_ceilings[path]:
            widened.append(f"{path}: ceiling {ceiling}, {main_ceilings[path]} on {MAIN}")
    return widened


def report(problems: list[str], advice: str) -> str:
    return "\n".join([advice, *problems])


@pytest.fixture(scope="module")
def sizes():
    return code_sizes()


@pytest.fixture(scope="module")
def ceilings():
    return read_allow_list()


def test_no_file_outside_the_list_passes_its_cap(sizes, ceilings):
    problems = unlisted_over_cap(sizes, ceilings)
    assert not problems, report(problems, "Split these files by responsibility; the list takes no new files:")


def test_no_listed_file_grows_past_its_ceiling(sizes, ceilings):
    problems = over_ceiling(sizes, ceilings)
    assert not problems, report(problems, f"These files may not grow; their ceiling is in {ALLOW_LIST}:")


def test_the_list_only_names_files_still_over_their_cap(sizes, ceilings):
    problems = stale_entries(sizes, ceilings)
    assert not problems, report(problems, f"Take these entries out of {ALLOW_LIST}:")


def test_each_ceiling_follows_its_file_down(sizes, ceilings):
    problems = loose_ceilings(sizes, ceilings)
    assert not problems, report(problems, f"Lower these ceilings in {ALLOW_LIST}:")


def test_the_list_only_shrinks_against_main(ceilings):
    main_ceilings = main_allow_list()
    if main_ceilings is None:
        return
    problems = widened_entries(ceilings, main_ceilings)
    assert not problems, report(problems, f"{ALLOW_LIST} may only shrink against {MAIN}:")


def test_a_last_line_without_its_newline_counts():
    assert [physical_lines(data) for data in (b"", b"a\n", b"a\nb", b"a\n\n")] == [
        0,
        1,
        2,
        2,
    ]


@pytest.mark.parametrize(
    ("path", "test"),
    [
        ("billing/tests/helpers.py", True),
        ("tests/e2e/panel/fixtures.ts", True),
        ("accounts/frontend/__tests__/mount-panel.ts", True),
        ("conftest.py", True),
        ("hubs/test_rules.py", True),
        ("frontend/main.test.ts", True),
        ("tests/e2e/public-web.spec.ts", True),
        ("billing/services.py", False),
        ("frontend/sdk-types.d.ts", False),
        ("billing/frontend/latest.ts", False),
        ("scripts/contest.sh", False),
    ],
)
def test_tests_and_production_have_their_own_cap(path, test):
    assert cap_of(path) == (TEST_CAP if test else PRODUCTION_CAP)


@pytest.mark.parametrize(
    ("path", "generated"),
    [
        ("hubs/migrations/0013_plans_in_the_database.py", True),
        ("static/vendor/ionic/css/core.css", True),
        ("frontend/dist/assets/index.js", True),
        ("public/static/public/theme.css", False),
        ("frontend/generated/operation-routes.ts", False),
        ("hubs/tests/test_migrations.py", False),
    ],
)
def test_only_what_nobody_writes_by_hand_is_left_out(path, generated):
    assert is_generated(path) is generated


def test_a_file_outside_the_list_over_its_cap_is_reported():
    sizes = {
        "a/services.py": 1001,
        "a/queries.py": 1000,
        "a/tests/test_x.py": 1501,
        "a/tests/test_y.py": 1500,
    }
    assert unlisted_over_cap(sizes, {"b/models.py": 1200}) == [
        "a/services.py: 1001 lines, over its cap of 1000",
        "a/tests/test_x.py: 1501 lines, over its cap of 1500",
    ]
    assert unlisted_over_cap(sizes, {"a/services.py": 1100, "a/tests/test_x.py": 1600}) == []


def test_a_listed_file_past_its_ceiling_is_reported():
    sizes = {"a/services.py": 1201, "a/queries.py": 1200}
    assert over_ceiling(sizes, {"a/services.py": 1200, "a/queries.py": 1200}) == [
        "a/services.py: 1201 lines, over its ceiling of 1200"
    ]


def test_an_entry_gone_or_within_its_cap_is_reported():
    sizes = {"a/services.py": 1000, "a/tests/test_x.py": 1500, "a/queries.py": 1001}
    ceilings = {
        "a/services.py": 1100,
        "a/tests/test_x.py": 1600,
        "a/queries.py": 1100,
        "a/gone.py": 1500,
    }
    assert stale_entries(sizes, ceilings) == [
        "a/services.py: 1000 lines, it fits its cap of 1000",
        "a/tests/test_x.py: 1500 lines, it fits its cap of 1500",
        "a/gone.py: no code file of this repository is measured at this path",
    ]


def test_a_ceiling_left_above_a_shrunk_file_is_reported():
    sizes = {"a/services.py": 5099, "a/queries.py": 5101, "a/models.py": 1100}
    ceilings = {"a/services.py": 5200, "a/queries.py": 5200, "a/models.py": 1100}
    assert loose_ceilings(sizes, ceilings) == ["a/services.py: 5099 lines, lower its ceiling from 5200 to 5100"]


def test_the_list_may_not_gain_a_path_or_raise_a_ceiling_against_main():
    main = {"a.py": 1200, "b.py": 1200, "c.py": 1300, "d.py": 1100}
    ceilings = {"a.py": 1200, "b.py": 1300, "c.py": 1200, "e.py": 1100}
    assert widened_entries(ceilings, main) == [
        "b.py: ceiling 1300, 1200 on origin/main",
        "e.py: not listed on origin/main",
    ]


def test_the_list_reads_its_entries_and_skips_notes():
    text = "# <ceiling> <path> <issue>\n\n5200 billing/services.py saas#1\n1800 hubs/tests/test_migrations.py saas#1\n"
    assert parse_allow_list(text) == {
        "billing/services.py": 5200,
        "hubs/tests/test_migrations.py": 1800,
    }


@pytest.mark.parametrize(
    "text",
    [
        "5200 billing/services.py",
        "5200 billing/services.py hub#1",
        "52OO billing/services.py saas#1",
        " 5200 billing/services.py saas#1",
        "5200 billing/services.py saas#1 because",
        "5200 billing/services.py saas#1\n5300 billing/services.py saas#1",
    ],
)
def test_a_malformed_list_is_refused(text):
    with pytest.raises(ValueError, match=ALLOW_LIST):
        parse_allow_list(text)


def git_repo(root: Path) -> None:
    subprocess.run(["git", "init", "--quiet", "--initial-branch=main", str(root)], check=True)


def commit_as_main(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).write_text(text)
    identity = [
        "-c",
        "user.name=size",
        "-c",
        "user.email=size@example.com",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(["git", *identity, "add", "--all"], cwd=root, check=True)
    subprocess.run(["git", *identity, "commit", "--quiet", "-m", "main"], cwd=root, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=root, check=True)


def test_without_main_the_comparison_fails_instead_of_passing(tmp_path):
    git_repo(tmp_path)
    with pytest.raises(pytest.fail.Exception, match="git fetch origin main"):
        main_allow_list(tmp_path)


def test_main_without_a_list_yet_has_nothing_to_compare(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"README.md": "saas\n"})
    assert main_allow_list(tmp_path) is None


def test_the_list_on_main_is_read_from_main(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {ALLOW_LIST: "1200 billing/services.py saas#1\n"})
    (tmp_path / ALLOW_LIST).write_text("1300 billing/services.py saas#1\n")
    assert main_allow_list(tmp_path) == {"billing/services.py": 1200}


def test_new_code_files_count_before_they_are_added_and_ignored_ones_do_not(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {".gitignore": "scratch.py\n", "services.py": "a\nb\n"})
    for name, text in {
        "new.ts": "a\n",
        "scratch.py": "a\n",
        "README.md": "a\n",
        "hubs/migrations/0001_initial.py": "a\n",
    }.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    assert code_sizes(tmp_path) == {"new.ts": 1, "services.py": 2}
