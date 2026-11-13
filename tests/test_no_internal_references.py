"""Code is read by people who have never seen the project's planning documents.

Comments, docstrings, test names and log messages have to make sense on their own, so the code never
points at a plan section, a dated planning round, a delivery slice or phase, a task id or a dated plan
or spec, nor signs a decision with who took it and when. Their prose does not cite the codes of an internal
audit or review either: the reader has not seen it, so the reason is written out. Nor does it explain itself
with an issue of another of our repositories or of the old product, which the reader of this one cannot open,
nor with a work item's short label. Markdown files are left out: they are where the plans live. A dependency
patch is read too, and must not cite an issue of one of our repositories either: its comments land in the
dependency's code, far from our trackers.
"""

import ast
import io
import re
import subprocess
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Built from its code point so that this file does not trip its own scan.
SECTION_SIGN = "\N{SECTION SIGN}"

# The owner's name, kept in one place so that the patterns and the examples below do not trip the scan.
OWNER = "Ioan"

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
            r"\bPLAN-(?:HUB|SAAS|AWS|DB)\b",
        )
    )
)

# Who decided something and on which day. The reason stays in the comment; the person and the date are in the
# history. A name as data (a fixture's first name, an address) signs nothing and is left alone.
AUTHORSHIP = re.compile(
    "|".join(
        (
            rf"\({OWNER}[,;:)]",
            rf"\b{OWNER}, 20[0-9]{{2}}",
            rf"\b{OWNER}:",
            rf"\b{OWNER}'s (rule|decision|call|choice|request)",
            rf"[Dd]ecisi[oó]n (de|of) {OWNER}\b",
            rf"20[0-9]{{2}}-[0-9]{{2}}(-[0-9]{{2}})?[,;:]? {OWNER}\b",
        )
    )
)

OUR_REPO_ISSUE = re.compile(r"(?<![\w-])(?:hub|saas|ui|live|aws|app|outfitkit|pm|knowledge)#[0-9]+")

# Our other repositories, and the old product's: its modules, its design kit and its trackers, now archived.
OTHER_REPOSITORIES = (
    *("3d", "app", "aws", "blueprints", "corpus", "docs", "erplora-next", "hub", "knowledge", "live", "qa", "ui"),
    *("ai-cluster", "appointments", "architecture", "attendance", "backup", "cart_checkout", "cash_register"),
    *("combos", "customers", "ERPlora-Bridge-android", "ERPloraKiosk", "flows", "infra", "inventory", "invoice"),
    *("kitchen", "kitchen_orders", "modifiers", "module-toolkit", "network-kit", "online_booking", "orders"),
    *("outfitkit", "payments", "pm", "pricing", "printing", "reservations", "sales", "schedules", "services"),
    *("setup", "staff", "tables", "tasks", "taxes", "verifactu", "verifactu-gateway", "warehouse", "whatsapp_inbox"),
)

# An issue of one of those, which the reader of this repository cannot open: the reason is written out instead.
# An issue of a third party's project stays, as does a colour or one of this repository's own issues.
OTHER_REPO_ISSUE = re.compile(
    r"(?<![\w/.:-])(?:gh:)?(?:ERPlora/)?(?:" + "|".join(map(re.escape, OTHER_REPOSITORIES)) + r")#[0-9]+"
    r"|\berplora-old/[\w.-]+#[0-9]+"
)

# The old product's tracker was called saas as well, and its numbers run far past this repository's: one of them
# cited here opens an unrelated issue, or none. A number well beyond the newest merged pull request is one of those.
THIS_TRACKER_ISSUE = re.compile(r"(?<![\w/.:-])(?:gh:)?(?:ERPlora/)?saas#([0-9]+)|\b[Ii]ssue #([0-9]+)")
OLD_TRACKER_MARGIN = 100
MERGED_PULL_REQUEST = re.compile(r"\(#([0-9]+)\)|^Merge pull request #([0-9]+)", re.MULTILINE)

# A work item's short label, a capital letter and a number, says nothing to the reader: the fact it stood for is
# written instead. A Django check (hubs.W002), a standard's chapter (ASVS V6.3.7), an API's version (SigV4, v25.0)
# or one of the AEAT's lists («L3», list L2) has another shape.
WORK_LABEL = re.compile(r"(?<![\w.«-])(?<!list )(?<!lista )[LVW][0-9]{1,2}[a-z]?(?![\w.»-])")

PATCH_SUFFIX = ".patch"

# The end-to-end specs name their screenshots after the task that added them, and renaming those
# string literals would orphan the evidence already captured. There only comments and test titles
# are read.
E2E_DIR = "tests/e2e/"
E2E_SCRIPT_SUFFIXES = {".ts", ".js", ".mjs"}
COMMENT_OR_STRING = re.compile(r"""//.*|'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`""")
TEST_TITLE_OPENER = re.compile(r"\b(?:test|it|describe)(?:\.\w+)*\(\s*$")

# The codes of an internal audit or review: a finding's letter and number, a delivery lot, a review's numbered
# finding and the audit's own name and date. The same shape is data elsewhere (an invoice series, a capture
# key), so they are only looked for in prose: comments, docstrings and test titles. A ruling of the Court of
# Justice has a year after a slash and is not one of them.
AUDIT_CODE = re.compile(
    "|".join(
        (
            r"(?<![\w\[\^-])[A-Z]-(?:[0-9]{2}|[A-Z][0-9])(?!\w|/[0-9])",
            r"(?<![\w\[\^-])L[0-9]-[A-Z][0-9]?(?!\w|/[0-9])",
            r"\bUX-AUDIT-[0-9]+",
            r"\b[Aa]udit (?:of )?(?:2\b|20[0-9]{2}-)",
            r"\b[Ff]inding [0-9]+\)",
        )
    )
)

SCRIPT_SUFFIXES = {".ts", ".js", ".mjs", ".vue", PATCH_SUFFIX}
LINE_COMMENTS = {
    **dict.fromkeys(SCRIPT_SUFFIXES, ("//",)),
    **dict.fromkeys((".sh", ".toml", ".yml", ".yaml"), ("#",)),
    ".ini": ("#", ";"),
    ".sql": ("--",),
}
BLOCK_COMMENTS = {
    **dict.fromkeys((".ts", ".js", ".mjs", PATCH_SUFFIX, ".css", ".sql"), {"/*": "*/"}),
    ".vue": {"/*": "*/", "<!--": "-->"},
    ".html": {"<!--": "-->", "{#": "#}", "{% comment %}": "{% endcomment %}"},
}
PATCH_HEADERS = ("+++", "---", "@@", "diff ", "index ")

CODE_SUFFIXES = {
    PATCH_SUFFIX,
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

# A generated file repeats its generator's strings word for word, and a test compares the two: its comments are
# read as the generator's lines are, for plans and signatures, but not as prose of their own.
GENERATED_FILES = {"public/static/public/ionic-utilities.css"}

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


def prose_lines(path, text):
    """Line number → the prose on it: its comments, its docstrings and its test titles."""
    suffix = Path(path).suffix
    if suffix == ".py":
        return python_prose(text)
    return marked_prose(suffix, text)


def python_prose(text):
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
        comments = [t for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
    except (SyntaxError, tokenize.TokenError):
        # A file that does not parse yet is read whole rather than not at all.
        return dict(enumerate(lines, 1))
    prose = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for number in range(node.lineno, node.end_lineno + 1):
                prose[number] = lines[number - 1]
    for comment in comments:
        number = comment.start[0]
        prose[number] = prose.get(number, "") + " " + comment.string
    return prose


def marked_prose(suffix, text):
    """The comments of a file whose comments are marked (``//``, ``/* */``, ``<!-- -->``, ``#``…) and, in a
    script, the titles of its tests; every other string literal is left out."""
    quotes = "'\"`" if suffix in SCRIPT_SUFFIXES else "'\""
    blocks = BLOCK_COMMENTS.get(suffix, {})
    tokens = re.compile(
        "|".join(
            [re.escape(marker) + ".*" for marker in LINE_COMMENTS.get(suffix, ())]
            + [re.escape(opener) for opener in blocks]
            + [rf"{q}(?:[^{q}\\]|\\.)*{q}" for q in quotes]
        )
    )
    script = suffix in SCRIPT_SUFFIXES
    patch = suffix == PATCH_SUFFIX
    prose = {}
    closer = None
    title_next = False
    for number, line in enumerate(text.splitlines(), 1):
        if patch:
            if line.startswith(PATCH_HEADERS):
                closer, title_next = None, False
                continue
            line = line[1:]
            # A hunk can start inside a doc comment, after its opener.
            if closer is None and line.lstrip().startswith("*"):
                prose[number] = line
                continue
        pieces = []
        position = 0
        while position < len(line):
            if closer:
                end = line.find(closer, position)
                if end < 0:
                    pieces.append(line[position:])
                    break
                pieces.append(line[position:end])
                position, closer = end + len(closer), None
                continue
            match = tokens.search(line, position)
            if not match:
                break
            token = match.group(0)
            if token in blocks:
                closer = blocks[token]
            elif token[0] not in quotes:
                pieces.append(token)
            elif script:
                before = line[: match.start()]
                if TEST_TITLE_OPENER.search(before) or (title_next and not before.strip()):
                    pieces.append(token)
            position = match.end()
        title_next = script and closer is None and bool(TEST_TITLE_OPENER.search(line))
        if pieces:
            prose[number] = " ".join(pieces)
    return prose


def newest_merged_number(root=REPO):
    """The number of the newest pull request in the history, or ``None`` without one. A shallow clone, as the CI
    checks out, holds a commit or two: the number it names, if any, says nothing of the newest, so none is read."""

    def git(*args):
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False).stdout

    if git("rev-parse", "--is-shallow-repository").strip() != "false":
        return None
    subjects = git("log", "-n", "200", "--format=%s")
    numbers = [int(match.group(1) or match.group(2)) for match in MERGED_PULL_REQUEST.finditer(subjects)]
    return max(numbers, default=None)


def old_tracker_issue(prose, newest):
    """The first issue cited in ``prose`` that is the old product's, known by its number; without the newest
    merged number to compare with, none is."""
    if newest is None:
        return None
    for match in THIS_TRACKER_ISSUE.finditer(prose):
        if int(match.group(1) or match.group(2)) > newest + OLD_TRACKER_MARGIN:
            return match
    return None


def internal_references(paths, root=REPO, newest=None):
    found = []
    for path in paths:
        if path in FROZEN_FILES:
            continue
        e2e_script = path.startswith(E2E_DIR) and Path(path).suffix in E2E_SCRIPT_SUFFIXES
        text = (root / path).read_text(encoding="utf-8", errors="replace")
        patch = Path(path).suffix == PATCH_SUFFIX
        prose = prose_lines(path, text)
        for number, line in enumerate(text.splitlines(), 1):
            unquoted = without_string_literals(line) if e2e_script else line
            for clause in QUOTED_CLAUSES:
                unquoted = unquoted.replace(clause, "")
            line_prose = "" if path in GENERATED_FILES else prose.get(number, "")
            reference = (
                INTERNAL_REFERENCE.search(unquoted)
                or AUTHORSHIP.search(unquoted)
                or AUDIT_CODE.search(line_prose)
                or OTHER_REPO_ISSUE.search(line_prose)
                or WORK_LABEL.search(line_prose)
                or old_tracker_issue(line_prose, newest)
            )
            if reference or (patch and OUR_REPO_ISSUE.search(line)):
                found.append(f"{path}:{number}: {line.strip()}")
    return found


def test_code_never_points_at_internal_plans():
    paths = code_files()
    assert "tests/test_no_internal_references.py" in paths, "git ls-files listed no code"
    found = internal_references(paths, newest=newest_merged_number())
    assert not found, (
        "Code that points at internal plans, rounds, slices, audits, work labels or another repository's issues, or "
        "signs a decision:\n" + "\n".join(found)
    )


@pytest.mark.parametrize(
    "text",
    [
        "Voice and video calls (Plan " + SECTION_SIGN + "66)",
        "see PLAN" + "-SAAS " + SECTION_SIGN + "47",
        "PLAN.md" + SECTION_SIGN + "5",
        "the limits of " + SECTION_SIGN + "14.2",
        "PLAN" + "-HUB round " + "2026-10-21",
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
        "a private bucket (PLAN" + "-AWS «s3_downloads.tf»)",
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
        "<!-- PLAN CARDS -->",
    ],
)
def test_the_scan_leaves_ordinary_text_alone(text):
    assert not INTERNAL_REFERENCE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        f"One line, not a stack of links ({OWNER}, 2026-10-14: a clean page).",
        f"reCAPTCHA, invisible (accounts/frontend/recaptcha.ts; {OWNER}, 2026-10-22)",
        f"what it is built with ({OWNER},",
        f"the presigned link of each ({OWNER})",
        f"{OWNER}'s rule (2026-10-15): the code is always mailed",
        f"the default since 2026-10-23; {OWNER}: the WAF on the ALB",
        f"por decisión de {OWNER} del 2026-10-14",
        f"(2026-10-15, {OWNER})",
    ],
)
def test_the_scan_catches_each_kind_of_signature(text):
    assert AUTHORSHIP.search(text)


@pytest.mark.parametrize(
    "text",
    [
        f'first_name="{OWNER}", last_name="Beilic", language="es"',
        'override_by="ioan@erplora.com"',
        f"const name = '{OWNER} Beilic';",
        f"Hello, {OWNER}",
        "the deadline (Friday, 2026-11-07)",
    ],
)
def test_the_scan_leaves_a_name_as_data_alone(text):
    assert not AUTHORSHIP.search(text)


def test_the_dependency_patches_are_read():
    patches = {p.relative_to(REPO).as_posix() for p in (REPO / "patches").glob("*.patch")}
    assert patches <= set(code_files())


def test_a_patch_comment_that_cites_an_issue_of_another_repo_is_caught(tmp_path):
    (tmp_path / "patches").mkdir()
    (tmp_path / "patches" / "some-lib@1.0.0.patch").write_text(
        " const a = 1;\n"
        "+ * one page at a time (hub#2242)\n"
        "+ * see PLAN " + SECTION_SIGN + "3\n"
        "+ * upstream capacitor-app#41 and color #123456 stay\n",
        encoding="utf-8",
    )
    assert internal_references(["patches/some-lib@1.0.0.patch"], root=tmp_path) == [
        "patches/some-lib@1.0.0.patch:2: + * one page at a time (hub#2242)",
        "patches/some-lib@1.0.0.patch:3: + * see PLAN " + SECTION_SIGN + "3",
    ]


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


def test_a_signature_with_its_date_is_caught_and_a_name_as_data_is_not(tmp_path):
    (tmp_path / "accounts").mkdir()
    (tmp_path / "accounts" / "flow.py").write_text(
        f'"""The code is always mailed ({OWNER}, 2026-10-15)."""\n'
        f'BUYER = {{"first_name": "{OWNER}", "last_name": "Beilic", "email": "ioan@erplora.com"}}\n'
        f"# Off by default since 2026-10-23; {OWNER}: the WAF on the load balancer is enough.\n"
        f"# {OWNER}'s rule (2026-10-15): one code per sign-in.\n",
        encoding="utf-8",
    )
    (tmp_path / "accounts" / "Card.vue").write_text(
        '<script setup lang="ts">\n'
        f"// One line, not a stack of links ({OWNER},\n"
        "// 2026-10-14).\n"
        f"const name = '{OWNER}';\n",
        encoding="utf-8",
    )
    found = internal_references(["accounts/flow.py", "accounts/Card.vue"], root=tmp_path)
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "accounts/flow.py:1",
        "accounts/flow.py:3",
        "accounts/flow.py:4",
        "accounts/Card.vue:2",
    ]


def test_a_quoted_clause_of_an_outside_contract_is_not_a_reference(tmp_path):
    (tmp_path / "quote.py").write_text('NOTE = "' + QUOTED_CLAUSES[0] + '"\n', encoding="utf-8")
    (tmp_path / "plan.py").write_text('NOTE = "PLAN ' + SECTION_SIGN + '3"\n', encoding="utf-8")
    assert internal_references(["quote.py", "plan.py"], root=tmp_path) == [
        'plan.py:1: NOTE = "PLAN ' + SECTION_SIGN + '3"'
    ]


@pytest.mark.parametrize(
    "text",
    [
        "a wrong current password is said in the panel's words (audit 2 R-26)",
        "a failure is said with «Retry» (audit 2026-10-14, R-04/R-08)",
        "as with the SSE down in the audit of 2026-10-14",
        "the dialog behind as deep as FormModal says (UX audit U-90)",
        "every target is 44 px (W-F6, W-13 of the mockups)",
        "for that business (UX-AUDIT-4 W-F2/X-03/V-37)",
        "lives in a landmark of its own (S-05: axe `region`)",
        "the views of the account plane (hubs 0007, L1-A2)",
        "the Account page's models (0006, L3-A)",
        "a downgrade waits for the end of the period (review of L3-C)",
        "the safety net of unpaid plans (lot L2-B)",
        "not Las Palmas: no 0 % by a guess (finding 1)",
        "WCAG 1.4.4 (audit R-02): no maximum-scale",
    ],
)
def test_the_scan_catches_each_kind_of_audit_code(text):
    assert AUDIT_CODE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "treated as VAT-included (TJUE *Tulică* C-249/12 and C-250/12)",
        "CJEU C-375/15 (BAWAG): the email is the notice",
        "the ruling in case C-41/14",
        "the invoice A-1 of the series A is cancelled",
        "BASE-F12: a flow of the Hub's WORKBOOK",
        "ACCOUNTS-G93: «Sign out» in the user menu",
        "decoded as UTF-8, dated as ISO-8601",
        "a COVID-19 surcharge",
        "the characters [A-Z0-9] and [^A-Z0-9]",
        "the audit log keeps 90 days",
        "the audit entries older than 90 days",
        "after finding 3 rows the loop stops",
    ],
)
def test_the_scan_leaves_rulings_series_and_flows_alone(text):
    assert not AUDIT_CODE.search(text)


def found_lines(found):
    return [int(line.split(":")[1]) for line in found]


def test_an_audit_code_is_caught_in_python_prose_but_not_in_its_data(tmp_path):
    (tmp_path / "billing").mkdir()
    lines = (
        '"""The numbers of the invoices (lot L3-C)."""',
        'SERIES = "A-1"',
        "# W-19: the toolbar measures its own row.",
        'note = CharField(help_text="kept as it was (review of L2-A)")',
        "",
        "",
        "def test_the_first_name_is_required():",
        '    """Audit 2 S-10: a blank first name',
        '    was saved (finding 1)."""',
        '    sent = "<sum1:NumSerieFacturaAnulada>A-1</sum1:NumSerieFacturaAnulada>"',
        "    return sent  # VAT-inclusive (TJUE C-249/12 and C-250/12)",
    )
    (tmp_path / "billing" / "numbers.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["billing/numbers.py"], root=tmp_path)) == [1, 3, 8, 9]


def test_an_audit_code_is_caught_in_a_script_comment_or_test_title_but_not_in_a_capture_key(tmp_path):
    spec = tmp_path / "tests" / "e2e" / "panel" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    lines = (
        "// The toolbar on one line (audit 2026-10-14, R-14).",
        "const series = 'A-1';",
        "const key = 'R-05';",
        "it('waits for an address (audit 2 R-32)', () => {",
        "  expect(key).toBe(series); /* W-F2 */ expect(1).toBe(1);",
        "});",
        "test(",
        "  'refused (R-05): a toast says why',",
        "  async () => {",
        "    await shot('R-05-desktop'); // the capture keeps its key",
        "    /* the row is measured on its own box,",
        "       as the table fits its columns (W-19) */",
        "    const ruling = 'C-249/12'; // TJUE C-249/12",
        "  },",
        ");",
    )
    spec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert found_lines(internal_references(["tests/e2e/panel/some.spec.ts"], root=tmp_path)) == [1, 4, 5, 8, 12]


def test_an_audit_code_is_caught_in_the_comments_of_a_component_a_template_and_a_patch(tmp_path):
    (tmp_path / "accounts").mkdir()
    (tmp_path / "patches").mkdir()
    (tmp_path / "accounts" / "Row.vue").write_text(
        "<template>\n"
        "  <!-- the Google row (U-63) -->\n"
        "  <p class=\"note\">{{ t('R-05') }}</p>\n"
        "</template>\n"
        '<script setup lang="ts">\n'
        "// The first name is required (audit 2 S-10).\n"
        'const series = "A-1";\n'
        "</script>\n"
        "<style scoped>\n"
        "/* 44 px targets on a phone\n"
        "   (W-F6, W-13 of the mockups) */\n"
        "</style>\n",
        encoding="utf-8",
    )
    (tmp_path / "accounts" / "page.html").write_text(
        "{# The security lists (audit 2 R-10) #}\n"
        '<p data-series="A-1">R-02</p>\n'
        "<!-- R-02: no maximum-scale -->\n",
        encoding="utf-8",
    )
    (tmp_path / "patches" / "some-lib@1.0.0.patch").write_text(
        "diff --git a/dist/index.js b/dist/index.js\n"
        "--- a/dist/index.js\n"
        "+++ b/dist/index.js\n"
        "@@ -1,3 +1,4 @@\n"
        "   * one page at a time\n"
        "+  * and its title may wrap (R-25)\n"
        "+ const series = 'R-25';\n",
        encoding="utf-8",
    )
    found = internal_references(
        ["accounts/Row.vue", "accounts/page.html", "patches/some-lib@1.0.0.patch"], root=tmp_path
    )
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "accounts/Row.vue:2",
        "accounts/Row.vue:6",
        "accounts/Row.vue:11",
        "accounts/page.html:1",
        "accounts/page.html:3",
        "patches/some-lib@1.0.0.patch:6",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Android has no fallback (hub#984): its only channel is Google Play",
        "FormModal keeps both since ERPlora/ui#112",
        "Meta not answering is said as Meta's (gh:hub#2731)",
        "the plain-language half of the update policy (pm#69)",
        "Canonical = the Hub's develop (ERPlora issue outfitkit#14)",
        "a separator, never as text (ui#56)",
        "the chain of the records, as verifactu#12 left it",
        "the old till's cash_register#7",
        "erplora-old/saas#2536: the address is changed in two steps",
    ],
)
def test_the_scan_catches_an_issue_of_another_repository(text):
    assert OTHER_REPO_ISSUE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the doors' spec, which no screen covers (saas#89)",
        "a request is answered for its real path (ERPlora/saas#89)",
        "fixed upstream in capacitor-app#41",
        "the colour #123456 of the border",
        "the business's hub #3 in the list",
        "UTS #46, which also folds the case",
        "fi:saas/orgs-users#informacion-de-facturacion",
        "https://github.com/ERPlora/hub/pull/12#issuecomment-1",
        "the C# client",
    ],
)
def test_the_scan_leaves_this_repository_and_third_parties_alone(text):
    assert not OTHER_REPO_ISSUE.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the address is changed in two steps (saas#2536)",
        "an address in its plain form, as today's SaaS (ERPlora/saas#1018)",
        "Meta's, never ERPlora's (gh:saas#958)",
        "Cookie-consent banner (issue #958)",
        "Issue #2344: the period lives on the item",
    ],
)
def test_the_scan_catches_an_issue_of_the_old_tracker(text):
    assert old_tracker_issue(text, newest=424)


@pytest.mark.parametrize(
    "text",
    [
        "the doors' spec, which no screen covers (saas#89)",
        "the newest pull request (saas#424)",
        "an issue opened since (saas#510)",
        "issue #12 of the list",
        "the grey #999 of the border",
    ],
)
def test_the_scan_leaves_this_trackers_issues_alone(text):
    assert not old_tracker_issue(text, newest=424)


def test_without_the_newest_number_no_issue_is_the_old_trackers():
    assert old_tracker_issue("the address is changed in two steps (saas#2536)", newest=None) is None


def test_the_newest_merged_number_is_read_from_the_whole_history_only(tmp_path):
    full = tmp_path / "full"
    full.mkdir()

    def commit(subject):
        subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=t", "-c", "user.email=t@example.com"]
            + ["commit", "--allow-empty", "-qm", subject],
            cwd=full,
            check=True,
        )

    assert newest_merged_number(full) is None
    subprocess.run(["git", "init", "-q"], cwd=full, check=True)
    assert newest_merged_number(full) is None
    commit("The first commit")
    assert newest_merged_number(full) is None
    commit("A fix that was squashed (#12)")
    commit("A fix of a fix (#9) (#10)")
    assert newest_merged_number(full) == 12
    commit("Merge pull request #15 from ERPlora/some-branch")
    assert newest_merged_number(full) == 15
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", full.as_uri(), str(shallow)], check=True)
    assert newest_merged_number(shallow) is None


@pytest.mark.parametrize(
    "text",
    [
        "ERPlora's staff is refused as a new invitation is (W11b)",
        "the toolbar keeps one row (W8/W10)",
        "until V3 generates them",
        "native buttons styled as the component (L8)",
        "the classes and the feature-card partial of L2;",
        "the four templates of the L3a port",
    ],
)
def test_the_scan_catches_a_work_label(text):
    assert WORK_LABEL.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "the system check ``hubs.W002`` names them",
        "the ALB redirects to HTTPS (W008)",
        "always told to its address (OWASP ASVS V6.3.7)",
        "the type of a rectifying invoice (AEAT, «L3» list)",
        "one of the values of list L2",
        "los valores de la lista L1",
        "a presigned URL signed with SigV4",
        "the Graph API v25.0",
        "since Stripe's ``2025-03-31.basil``",
        "allauth's ``/_allauth/browser/v1/account/email``",
        "a W3C recommendation",
        "a private S3 bucket, VAT regime S1, messages M1 and M2",
    ],
)
def test_the_scan_leaves_standards_versions_and_checks_alone(text):
    assert not WORK_LABEL.search(text)


def test_another_repositorys_issue_or_a_work_label_is_caught_in_prose_but_not_in_data(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "downloads.py").write_text(
        '"""Android has no fallback (hub#984): its only channel is Google Play."""\n'
        'ISSUE = "hub#984"\n'
        "LABEL = 'W11b'\n"
        "# The doors' spec, which no screen covers (saas#89).\n"
        "# The address is changed in two steps (saas#2536).\n"
        "# Refused as a new invitation is (W11b).\n"
        "# Treated as VAT-included (TJUE C-249/12); the invoice A-1 of the series A.\n",
        encoding="utf-8",
    )
    spec = tmp_path / "tests" / "e2e" / "panel" / "some.spec.ts"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "// Android never reads as a download (hub#984).\n"
        "it('paints a separator, never as text (ui#56)', async () => {\n"
        "  await shot('W11b-desktop');\n"
        "  test.info().annotations.push({ type: 'issue', description: 'hub#984' });\n"
        "});\n",
        encoding="utf-8",
    )
    (tmp_path / "public" / "page.html").write_text(
        "{# Never «Download»: on Android the only channel is Play (hub#984). #}\n"
        '<a href="#984">hub#984</a>\n',
        encoding="utf-8",
    )
    (tmp_path / "public" / "theme.css").write_text(
        "/* Canonical = the Hub's develop (outfitkit#14). */\n"
        ".row { color: #999; } /* the grey #999 of the border */\n",
        encoding="utf-8",
    )
    paths = ["public/downloads.py", "tests/e2e/panel/some.spec.ts", "public/page.html", "public/theme.css"]
    found = internal_references(paths, root=tmp_path, newest=424)
    assert [":".join(line.split(":")[:2]) for line in found] == [
        "public/downloads.py:1",
        "public/downloads.py:5",
        "public/downloads.py:6",
        "tests/e2e/panel/some.spec.ts:1",
        "tests/e2e/panel/some.spec.ts:2",
        "public/page.html:1",
        "public/theme.css:1",
    ]


def test_a_generated_file_is_read_for_plans_but_its_comments_are_its_generators(tmp_path):
    generated = tmp_path / "public" / "static" / "public" / "ionic-utilities.css"
    generated.parent.mkdir(parents=True)
    generated.write_text(
        "/* Card scope (saas#2536): Ionic's rules shadow layered ones (hub#984, W11b). */\n"
        "/* The bucket (PLAN" + "-AWS «s3_downloads.tf»). */\n",
        encoding="utf-8",
    )
    found = internal_references(["public/static/public/ionic-utilities.css"], root=tmp_path, newest=424)
    assert found_lines(found) == [2]
