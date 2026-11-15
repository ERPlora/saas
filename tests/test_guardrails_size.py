"""No code file grows past the size a person can still keep in their head.

Each language has its cap, counted in physical lines (blank lines and comments too, as ESLint's ``max-lines``):

- Python: 500 for production and 1,000 for tests.
- TypeScript and JavaScript: 300 for production and 500 for tests.
- Shell: a script past 100 lines is written in Python instead; a shell test has no figure of its own.
- CSS and Django templates have no figure of their own and keep 1,000 and 1,500.
- A Vue page is measured by blocks in the lint (``vue/max-lines-per-block``), not here.

Generated and third-party files do not count. The files over their cap are listed in ``.file-size-allow``, one per
line as ``<ceiling> <path> <issue>``, with the exact number of lines they had when the list froze them. That list
only shrinks: a listed file never grows past its ceiling, its ceiling comes down to the file's size as it shrinks,
it leaves the list once it fits its cap, and compared with the list where the branch left ``origin/main`` (their
merge base) the list gains no path and raises no ceiling. Two paths may enter it: a ``services.py``,
``queries.py`` or ``schemas.py`` moved whole to ``<name>/__init__.py`` takes its entry along, and when a cap comes
down the files main already had over it enter at their size there. The caps only come down too: against that same
merge base none rises and no measured suffix stops being measured.
"""

import ast
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ALLOW_LIST = ".file-size-allow"
SELF = "tests/test_guardrails_size.py"
MAIN = "origin/main"
BASE_NAME = f"the merge base with {MAIN}"

SCRIPT_CAPS = (300, 500)
OTHER_CAPS = (1000, 1500)
# Production and test cap of each measured suffix.
CAPS = {
    ".py": (500, 1000),
    ".ts": SCRIPT_CAPS,
    ".tsx": SCRIPT_CAPS,
    ".js": SCRIPT_CAPS,
    ".mjs": SCRIPT_CAPS,
    ".cjs": SCRIPT_CAPS,
    ".sh": (100, 1500),
    ".css": OTHER_CAPS,
    ".html": OTHER_CAPS,
}
# The modules other code imports by name: they become a package before anything new goes next to them.
DOOR_MODULES = frozenset({"services.py", "queries.py", "schemas.py"})

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
    production, test = CAPS[Path(path).suffix]
    return test if is_test(path) else production


def code_sizes(root: Path = REPO) -> dict[str, int]:
    """Lines of every code file git tracks or would track (new files count before they are added)."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode()
    paths = {path for path in listing.split("\0") if Path(path).suffix in CAPS and not is_generated(path)}
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


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def main_base(root: Path = REPO) -> str:
    """The commit where this branch left ``origin/main``: the exceptions are compared with that one, so a branch
    cut before main lowered a ceiling does not fail for a change it never saw.

    Without ``origin/main`` the comparison cannot be made, and that fails instead of passing quietly: the workflow
    that runs the suite fetches main, and a local tree only needs ``git fetch origin main``.
    """
    if git(root, "rev-parse", "--verify", "--quiet", f"{MAIN}^{{commit}}").returncode != 0:
        pytest.fail(f"{MAIN} is not in this clone, so the exceptions cannot be compared: git fetch origin main")
    base = git(root, "merge-base", "HEAD", MAIN)
    if base.returncode != 0:
        pytest.fail(f"HEAD has no history in common with {MAIN}, so the exceptions cannot be compared")
    return base.stdout.strip()


def main_text(name: str, root: Path = REPO) -> str | None:
    """The file ``name`` where this branch left ``origin/main``, or None when main did not have it there."""
    base = main_base(root)
    if git(root, "cat-file", "-e", f"{base}:{name}").returncode != 0:
        return None
    shown = git(root, "show", f"{base}:{name}")
    assert shown.returncode == 0, shown.stderr
    return shown.stdout


def main_allow_list(root: Path = REPO) -> dict[str, int] | None:
    """The list at the merge base with ``origin/main``, or None while main has none (the change that brings it in)."""
    text = main_text(ALLOW_LIST, root)
    return None if text is None else parse_allow_list(text)


def main_sizes(paths: Iterable[str], root: Path = REPO) -> dict[str, int]:
    """The lines each of ``paths`` had where this branch left ``origin/main``, leaving out those main did not have."""
    base = main_base(root)
    sizes = {}
    for path in paths:
        if git(root, "cat-file", "-e", f"{base}:{path}").returncode == 0:
            shown = subprocess.run(["git", "show", f"{base}:{path}"], cwd=root, capture_output=True, check=True)
            sizes[path] = physical_lines(shown.stdout)
    return sizes


def caps_in(source: str) -> dict[str, tuple[int, int]] | None:
    """The ``CAPS`` table as ``source``, the text of this test, sets it; None when it has no such table."""
    pairs: dict[str, tuple[int, int]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id == "CAPS":
            return {
                key.value: pairs[value.id] if isinstance(value, ast.Name) else ast.literal_eval(value)
                for key, value in zip(node.value.keys, node.value.values, strict=True)
            }
        if isinstance(node.value, ast.Tuple):
            pairs[node.targets[0].id] = ast.literal_eval(node.value)
    return None


def main_caps(root: Path = REPO) -> dict[str, tuple[int, int]] | None:
    """The caps where this branch left ``origin/main``, or None while main's test has no caps by language."""
    source = main_text(SELF, root)
    return None if source is None else caps_in(source)


def raised_caps(caps: dict[str, tuple[int, int]], caps_on_main: dict[str, tuple[int, int]]) -> list[str]:
    """Caps above the ones on main, and suffixes main measures that are no longer measured."""
    raised = []
    for suffix, on_main in caps_on_main.items():
        if suffix not in caps:
            raised.append(f"{suffix}: no longer measured, capped at {BASE_NAME}")
            continue
        for kind, now, before in zip(("production", "test"), caps[suffix], on_main, strict=True):
            if now > before:
                raised.append(f"{suffix}: {kind} cap {now}, {before} at {BASE_NAME}")
    return raised


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
    """Ceilings left above a file that shrank: they come down to its exact size."""
    return [
        f"{path}: {sizes[path]} lines, lower its ceiling from {ceiling} to {sizes[path]}"
        for path, ceiling in ceilings.items()
        if path in sizes and ceiling > sizes[path]
    ]


def moved_from(path: str, ceilings: dict[str, int], main_ceilings: dict[str, int]) -> str | None:
    """The listed door module that ``path`` is, moved whole from ``<name>.py`` to ``<name>/__init__.py``."""
    package, _, name = path.rpartition("/")
    module = f"{package}.py"
    moved = name == "__init__.py" and module.rpartition("/")[2] in DOOR_MODULES
    return module if moved and module in main_ceilings and module not in ceilings else None


def ceiling_on_main(
    path: str, ceilings: dict[str, int], main_ceilings: dict[str, int], sizes_on_main: dict[str, int]
) -> tuple[int, str] | None:
    """The highest ceiling ``path`` may have against main, with where it comes from; None when it may not be listed.

    ``sizes_on_main`` holds the lines main had at the listed paths its own list does not name.
    """
    if path in main_ceilings:
        return main_ceilings[path], f"{main_ceilings[path]} at {BASE_NAME}"
    module = moved_from(path, ceilings, main_ceilings)
    if module is not None:
        return main_ceilings[module], f"{main_ceilings[module]} at {BASE_NAME} as {module}"
    lines = sizes_on_main.get(path)
    if lines is not None and Path(path).suffix in CAPS and lines > cap_of(path):
        return lines, f"{lines} lines at {BASE_NAME}"
    return None


def widened_entries(
    ceilings: dict[str, int], main_ceilings: dict[str, int], sizes_on_main: dict[str, int]
) -> list[str]:
    widened = []
    for path, ceiling in ceilings.items():
        allowed = ceiling_on_main(path, ceilings, main_ceilings, sizes_on_main)
        if allowed is None:
            widened.append(f"{path}: not listed at {BASE_NAME}")
        elif ceiling > allowed[0]:
            widened.append(f"{path}: ceiling {ceiling}, {allowed[1]}")
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
    advice = f"These files may not grow past their ceiling in {ALLOW_LIST}; what a change adds goes to a new module:"
    assert not problems, report(problems, advice)


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
    sizes_on_main = main_sizes([path for path in ceilings if path not in main_ceilings])
    problems = widened_entries(ceilings, main_ceilings, sizes_on_main)
    assert not problems, report(problems, f"{ALLOW_LIST} may only shrink against {BASE_NAME}:")


def test_no_cap_rises_against_main():
    caps_on_main = main_caps()
    if caps_on_main is None:
        return
    problems = raised_caps(CAPS, caps_on_main)
    assert not problems, report(problems, f"A cap only comes down against {BASE_NAME}:")


def test_a_last_line_without_its_newline_counts():
    assert [physical_lines(data) for data in (b"", b"a\n", b"a\nb", b"a\n\n")] == [
        0,
        1,
        2,
        2,
    ]


@pytest.mark.parametrize(
    ("path", "cap"),
    [
        ("billing/services.py", 500),
        ("billing/tests/helpers.py", 1000),
        ("conftest.py", 1000),
        ("hubs/test_rules.py", 1000),
        ("frontend/sdk-types.d.ts", 300),
        ("billing/frontend/latest.ts", 300),
        ("scripts/gen-public-icons.mjs", 300),
        ("frontend/main.test.ts", 500),
        ("tests/e2e/panel/fixtures.ts", 500),
        ("accounts/frontend/__tests__/mount-panel.ts", 500),
        ("tests/e2e/public-web.spec.ts", 500),
        (".github/scripts/ecs-deploy.sh", 100),
        ("scripts/contest.sh", 100),
        ("docker/image.test.sh", 1500),
        ("public/static/public/theme.css", 1000),
        ("public/templates/public/base.html", 1000),
        ("billing/tests/fixtures/invoice.html", 1500),
    ],
)
def test_each_language_has_its_own_cap(path, cap):
    assert cap_of(path) == cap


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


def test_a_vue_page_is_left_to_the_lint_that_measures_its_blocks(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"Page.vue": "<template>\n" + "<p />\n" * 2000 + "</template>\n", "page.ts": "a\n"})
    assert code_sizes(tmp_path) == {"page.ts": 1}


def test_a_file_outside_the_list_over_its_cap_is_reported():
    sizes = {
        "a/services.py": 501,
        "a/queries.py": 500,
        "a/tests/test_x.py": 1001,
        "a/tests/test_y.py": 1000,
        "a/frontend/page.ts": 301,
        "a/frontend/list.ts": 300,
        "a/frontend/page.test.ts": 501,
        "a/frontend/list.test.ts": 500,
        "scripts/deploy.sh": 101,
        "scripts/build.sh": 100,
    }
    assert unlisted_over_cap(sizes, {"b/models.py": 1200}) == [
        "a/services.py: 501 lines, over its cap of 500",
        "a/tests/test_x.py: 1001 lines, over its cap of 1000",
        "a/frontend/page.ts: 301 lines, over its cap of 300",
        "a/frontend/page.test.ts: 501 lines, over its cap of 500",
        "scripts/deploy.sh: 101 lines, over its cap of 100",
    ]
    listed = {"a/services.py": 501, "a/tests/test_x.py": 1001, "a/frontend/page.ts": 301}
    listed |= {"a/frontend/page.test.ts": 501, "scripts/deploy.sh": 101}
    assert unlisted_over_cap(sizes, listed) == []


def test_a_listed_file_past_its_ceiling_is_reported():
    sizes = {"a/services.py": 1748, "a/queries.py": 1803}
    assert over_ceiling(sizes, {"a/services.py": 1747, "a/queries.py": 1803}) == [
        "a/services.py: 1748 lines, over its ceiling of 1747"
    ]


def test_an_entry_gone_or_within_its_cap_is_reported():
    sizes = {"a/services.py": 500, "a/tests/test_x.py": 1000, "a/queries.py": 501}
    ceilings = {
        "a/services.py": 510,
        "a/tests/test_x.py": 1010,
        "a/queries.py": 501,
        "a/gone.py": 1500,
    }
    assert stale_entries(sizes, ceilings) == [
        "a/services.py: 500 lines, it fits its cap of 500",
        "a/tests/test_x.py: 1000 lines, it fits its cap of 1000",
        "a/gone.py: no code file of this repository is measured at this path",
    ]


def test_a_ceiling_left_above_a_shrunk_file_comes_down_to_its_exact_size():
    sizes = {"a/services.py": 5167, "a/queries.py": 1803}
    ceilings = {"a/services.py": 5168, "a/queries.py": 1803}
    assert loose_ceilings(sizes, ceilings) == ["a/services.py: 5167 lines, lower its ceiling from 5168 to 5167"]


def test_the_list_may_not_gain_a_path_or_raise_a_ceiling_against_main():
    main = {"a.py": 1200, "b.py": 1200, "c.py": 1300, "d.py": 1100}
    ceilings = {"a.py": 1200, "b.py": 1201, "c.py": 1200, "e.py": 600, "f.py": 600}
    assert widened_entries(ceilings, main, {"f.py": 400}) == [
        "b.py: ceiling 1201, 1200 at the merge base with origin/main",
        "e.py: not listed at the merge base with origin/main",
        "f.py: not listed at the merge base with origin/main",
    ]


def test_a_file_main_already_had_over_a_lowered_cap_enters_the_list_at_most_at_its_size_there():
    main_sizes = {"hubs/models.py": 965, "hubs/admin.py": 965, "hubs/views.py": 500}
    ceilings = {"hubs/models.py": 965, "hubs/admin.py": 966, "hubs/views.py": 500}
    assert widened_entries(ceilings, {}, main_sizes) == [
        "hubs/admin.py: ceiling 966, 965 lines at the merge base with origin/main",
        "hubs/views.py: not listed at the merge base with origin/main",
    ]


@pytest.mark.parametrize("door", ["services", "queries", "schemas"])
def test_a_door_module_moved_whole_into_its_package_keeps_its_entry(door):
    assert widened_entries({f"hubs/{door}/__init__.py": 3126}, {f"hubs/{door}.py": 3126}, {}) == []


def test_that_move_is_the_only_new_path_and_it_never_raises_the_ceiling():
    main = {"hubs/services.py": 3126, "hubs/models.py": 965, "billing/queries.py": 1803}
    ceilings = {
        "hubs/services/__init__.py": 3127,
        "hubs/models/__init__.py": 965,
        "billing/queries.py": 1803,
        "billing/queries/__init__.py": 1803,
        "hubs/services/plans.py": 600,
    }
    assert widened_entries(ceilings, main, {}) == [
        "hubs/services/__init__.py: ceiling 3127, 3126 at the merge base with origin/main as hubs/services.py",
        "hubs/models/__init__.py: not listed at the merge base with origin/main",
        "billing/queries/__init__.py: not listed at the merge base with origin/main",
        "hubs/services/plans.py: not listed at the merge base with origin/main",
    ]


def test_a_cap_may_not_rise_or_stop_being_measured_against_main():
    main = {".py": (500, 1000), ".ts": (300, 500), ".js": (300, 500), ".sh": (100, 1500)}
    caps = {".py": (501, 1000), ".ts": (300, 501), ".js": (299, 400), ".css": (1000, 1500)}
    assert raised_caps(caps, main) == [
        ".py: production cap 501, 500 at the merge base with origin/main",
        ".ts: test cap 501, 500 at the merge base with origin/main",
        ".sh: no longer measured, capped at the merge base with origin/main",
    ]
    assert raised_caps(main, main) == []


def test_the_caps_are_read_from_the_source_of_this_test():
    assert caps_in(Path(__file__).read_text()) == CAPS


def test_a_source_without_caps_by_language_has_none_to_compare():
    assert caps_in("PRODUCTION_CAP = 1000\nTEST_CAP = 1500\n") is None


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


# A throwaway repository's commits: no global hooks, no signing, a fixed author.
LOCAL_GIT = ["-c", "user.name=size", "-c", "user.email=size@example.com", "-c", "core.hooksPath=/dev/null"]
LOCAL_GIT += ["-c", "commit.gpgsign=false"]


def local_git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *LOCAL_GIT, *args], cwd=root, check=True, capture_output=True, text=True).stdout


def commit_as_main(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).write_text(text)
    local_git(root, "add", "--all")
    local_git(root, "commit", "--quiet", "-m", "main")
    local_git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def main_moves_on_without_the_branch(root: Path, files: dict[str, str]) -> None:
    """Main gets a new commit after the branch in the working tree was cut from it."""
    local_git(root, "checkout", "--quiet", "-b", "branch")
    local_git(root, "checkout", "--quiet", "main")
    commit_as_main(root, files)
    local_git(root, "checkout", "--quiet", "branch")


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


def test_a_branch_cut_before_main_lowered_a_ceiling_compares_with_where_it_left_main(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {ALLOW_LIST: "1300 billing/services.py saas#1\n"})
    main_moves_on_without_the_branch(tmp_path, {ALLOW_LIST: "1200 billing/services.py saas#1\n"})
    assert (tmp_path / ALLOW_LIST).read_text() == "1300 billing/services.py saas#1\n"
    assert main_allow_list(tmp_path) == {"billing/services.py": 1300}


def test_a_branch_with_no_history_in_common_with_main_fails(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {ALLOW_LIST: "1200 billing/services.py saas#1\n"})
    empty_tree = local_git(tmp_path, "hash-object", "-t", "tree", "/dev/null").strip()
    unrelated = local_git(tmp_path, "commit-tree", empty_tree, "-m", "unrelated").strip()
    local_git(tmp_path, "update-ref", "refs/remotes/origin/main", unrelated)
    with pytest.raises(pytest.fail.Exception, match="no history in common"):
        main_allow_list(tmp_path)


def test_the_caps_on_main_are_read_from_this_test_where_the_branch_left_it(tmp_path):
    git_repo(tmp_path)
    (tmp_path / "tests").mkdir()
    commit_as_main(tmp_path, {SELF: 'BOTH = (500, 1000)\nCAPS = {".py": BOTH, ".sh": (100, 1500)}\n'})
    main_moves_on_without_the_branch(tmp_path, {SELF: 'CAPS = {".py": (400, 900)}\n'})
    (tmp_path / SELF).write_text('CAPS = {".py": (600, 1000)}\n')
    assert main_caps(tmp_path) == {".py": (500, 1000), ".sh": (100, 1500)}


def test_main_without_this_test_has_no_caps_to_compare(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"README.md": "saas\n"})
    assert main_caps(tmp_path) is None


def test_the_sizes_on_main_are_read_where_the_branch_left_it(tmp_path):
    git_repo(tmp_path)
    commit_as_main(tmp_path, {"models.py": "a\n" * 600})
    main_moves_on_without_the_branch(tmp_path, {"models.py": "a\n" * 700, "admin.py": "a\n"})
    (tmp_path / "models.py").write_text("a\n" * 650)
    assert main_sizes(["models.py", "admin.py", "gone.py"], tmp_path) == {"models.py": 600}


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
