"""Tests of e2e_report.py: the summary of the nightly e2e run and the one open issue it keeps about it.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

The script runs as the workflow runs it, with Playwright JSON reports written here and a fake gh CLI on the PATH that
answers the open issues and records its calls and the bodies it is given. Only the standard library: the workflow runs
it with the runner's python3.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import e2e_report

SCRIPT = Path(__file__).resolve().with_name("e2e_report.py")
TITLE = "Pruebas de navegador del SaaS en rojo en la pasada nocturna"
RUN = "https://github.com/ERPlora/saas/actions/runs/123"
SEARCH = f'gh issue list --state open --search "{TITLE}" in:title --limit 50 --json number,title'
SETTINGS = ("RESULT", "REPORT", "RUN_URL", "SHA")

FAKE_GH = """\
import os
import sys

args = sys.argv[1:]
call = " ".join(args)
with open(os.environ["CALLS_LOG"], "a", encoding="utf-8") as calls:
    calls.write("gh " + call + "\\n")
if os.environ.get("GH_FAILS") and os.environ.get("GH_FAILS_ON", "") in call:
    print("HTTP 502", file=sys.stderr)
    sys.exit(int(os.environ["GH_FAILS"]))
with open(os.environ["BODIES_LOG"], "a", encoding="utf-8") as bodies:
    for flag, value in zip(args, args[1:]):
        if flag == "--body-file":
            with open(value, encoding="utf-8") as body:
                bodies.write(body.read())
        elif flag == "--comment":
            bodies.write(value + "\\n")
if args[:2] == ["issue", "list"]:
    print(os.environ.get("OPEN_ISSUES", "[]"))
if args[:2] == ["issue", "create"]:
    print("https://github.com/ERPlora/saas/issues/99")
"""


def spec(title, line, tests, file="a.spec.ts"):
    return {"title": title, "file": file, "line": line, "tests": tests}


def red(*results, project="panel"):
    """A test that came out red, with the results Playwright gave it (none when not given)."""
    test = {"projectName": project, "status": "unexpected"}
    return {**test, "results": list(results)} if results else test


def error(message):
    return {"status": "failed", "error": {"message": message}}


STATS = {"expected": 1, "skipped": 0, "unexpected": 1, "flaky": 0}


def suite_of(*specs):
    return {"suites": [{"title": "a.spec.ts", "file": "a.spec.ts", "specs": list(specs)}], "errors": [], "stats": STATS}


def lines_of(test):
    return suite_of(spec("t", 1, [test]))


# A red test inside a describe of a public spec, a timed-out panel test, a passing and a skipped one, as Playwright's
# json reporter writes them (colours in the messages included).
RED = {
    "suites": [
        {
            "title": "public-web.spec.ts", "file": "public-web.spec.ts", "line": 0,
            "specs": [spec("passes", 2, [{"projectName": "public", "status": "expected"}], "public-web.spec.ts")],
            "suites": [{
                "title": "PUBLIC-F01 the home", "file": "public-web.spec.ts", "line": 3,
                "specs": [spec("shows the plans", 4, [red(error(
                    "Error: \u001b[2mexpect(\u001b[22mlocator).toBeVisible()\n\nExpected: visible"), project="public")],
                    "public-web.spec.ts")],
            }],
        },
        {
            "title": "panel/login.spec.ts", "file": "panel/login.spec.ts", "line": 0,
            "specs": [
                spec("skipped one", 2, [{"projectName": "panel", "status": "skipped"}], "panel/login.spec.ts"),
                spec("signs in", 9, [red(error("Test timeout of 120000ms exceeded."))], "panel/login.spec.ts"),
            ],
        },
    ],
    "errors": [],
    "stats": {"expected": 1, "skipped": 1, "unexpected": 2, "flaky": 0, "duration": 1000},
}
# A run that stopped in globalSetup: no test ran, the error is the run's.
SETUP = {"suites": [], "errors": [{"message": "Error: unapplied migrations (hubs.0042)\n    at globalSetup"}],
         "stats": {"expected": 0, "skipped": 0, "unexpected": 0, "flaky": 0, "duration": 10}}
OPEN = json.dumps([{"number": 43, "title": f"{TITLE} (otra)"}, {"number": 42, "title": TITLE}])

RED_DETAILS = (
    "2 en rojo · 1 bien · 1 saltadas\n"
    "\n"
    "- `[public] public-web.spec.ts:4` › PUBLIC-F01 the home › shows the plans — Error: expect(locator).toBeVisible()\n"
    "- `[panel] panel/login.spec.ts:9` › signs in — Test timeout of 120000ms exceeded.\n"
)
RED_HEADING = f"## Pruebas de navegador: en rojo\n\n{RUN} (commit `0123456`)\n\n"
GREEN_SUMMARY = f"## Pruebas de navegador: en verde\n\nLa pasada del 2026-11-06 ha salido en verde: {RUN}\n"
ISSUE_BODY = (
    "## Qué pasa\n"
    "Cada noche se prueban solas, en un navegador, todas las pantallas del SaaS (el panel de erplora.com y la web"
    " pública) sobre la última versión, y esta noche alguna ha fallado. Puede ser un fallo real que ya está en"
    " producción o una prueba que se ha quedado vieja: hasta que alguien lo mire no se sabe.\n"
    "\n"
    "## Propuesta\n"
    "Mirar cada prueba de la lista: si el fallo es del producto, arreglarlo con su prueba; si la prueba se quedó"
    " vieja, ponerla al día. Esta issue se cierra sola la primera noche en que la pasada salga entera en verde.\n"
    "\n"
    "## Detalle técnico\n"
    f"- Pasada del 2026-11-06: {RUN} (commit `0123456`). Las trazas y capturas de cada fallo, en su artefacto"
    " `e2e-test-results`.\n"
    "- Se repite una prueba desde `saas/` con `pnpm e2e:ci <spec>` (`tests/e2e/README.md`).\n"
    "\n"
    f"{RED_DETAILS}"
    "\n"
    "## Origen\n"
    "- Cómo se llegó: la pasada nocturna de las pruebas de navegador (`.github/workflows/nightly.yml`).\n"
    "- Sale de #296\n"
    "- La introdujo una PR: no comprobado — la pasada no sabe qué cambio la rompió; se busca entre los commits desde"
    " la última noche en verde.\n"
    "\n"
    "## Cómo se reproduce\n"
    f"- Run: {RUN}\n"
    "\n"
    "## Flujo\n"
    "- Flujo: ninguno — la pasada no sabe qué flujo prueba cada spec; el triaje lo pone al leerla.\n"
)


class NightCase(unittest.TestCase):
    """Runs e2e_report.py in a folder of its own; gh's calls, its bodies and the summary stay readable after."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.work = Path(folder.name)
        (self.work / "bin").mkdir()
        gh = self.work / "bin" / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}")
        gh.chmod(0o755)
        self.red_report = self.write("red.json", RED)

    def write(self, name, content):
        path = self.work / name
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return str(path)

    def report(self, **settings):
        """Runs the script with the night's settings, each overridable; None leaves one out. Returns its exit code."""
        for log in ("calls.log", "bodies.log", "summary"):
            (self.work / log).write_text("")
        env = {key: value for key, value in os.environ.items() if not key.startswith(("GITHUB_", "GH_"))}
        env |= {
            "PATH": f"{self.work / 'bin'}{os.pathsep}{os.environ['PATH']}", "GH_REPO": "ERPlora/saas", "GH_TOKEN": "x",
            "RUN_URL": RUN, "SHA": "0123456789abcdef", "DAY": "2026-11-06", "GITHUB_STEP_SUMMARY": self.path("summary"),
            "PUBLISH": "true", "RESULT": "failure", "REPORT": self.red_report, "OPEN_ISSUES": "[]",
            "CALLS_LOG": self.path("calls.log"), "BODIES_LOG": self.path("bodies.log"),
        }
        env |= settings
        env = {key: value for key, value in env.items() if value is not None}
        done = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, encoding="utf-8", check=False)
        self.stdout, self.stderr = done.stdout, done.stderr
        return done.returncode

    def path(self, name):
        return str(self.work / name)

    def read(self, name):
        return (self.work / name).read_text(encoding="utf-8")

    @property
    def calls(self):
        return re.sub(r"--body-file \S+/body\.md", "--body-file <body>", self.read("calls.log")).splitlines()

    @property
    def bodies(self):
        return self.read("bodies.log")

    @property
    def summary(self):
        return self.read("summary")


class RedNightTest(NightCase):
    def test_with_no_open_issue_it_opens_one_with_what_came_out_red(self):
        self.assertEqual(0, self.report())
        self.assertEqual([SEARCH, f"gh issue create --title {TITLE} --label prio:P1 --body-file <body>"], self.calls)
        self.assertEqual(ISSUE_BODY, self.bodies)
        self.assertNotIn("\x1b", self.bodies)
        self.assertNotIn("passes", self.bodies)
        self.assertNotIn("skipped one", self.bodies)
        self.assertEqual(RED_HEADING + RED_DETAILS, self.summary)
        self.assertEqual("https://github.com/ERPlora/saas/issues/99\n", self.stdout)

    def test_with_the_issue_open_it_comments_on_it_and_writes_nothing_else(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=OPEN))
        self.assertEqual([SEARCH, "gh issue comment 42 --body-file <body>"], self.calls)
        self.assertEqual(f"La pasada del 2026-11-06 sigue en rojo: {RUN} (commit `0123456`).\n\n{RED_DETAILS}",
                         self.bodies)

    def test_of_several_issues_of_that_exact_title_it_comments_on_the_newest(self):
        issues = [{"number": 42, "title": TITLE}, {"number": 44, "title": TITLE}, {"number": 50, "title": TITLE + " "}]
        self.assertEqual(0, self.report(OPEN_ISSUES=json.dumps(issues)))
        self.assertEqual([SEARCH, "gh issue comment 44 --body-file <body>"], self.calls)

    def test_a_gh_that_answers_nothing_has_no_open_issue(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=""))
        self.assertEqual([SEARCH, f"gh issue create --title {TITLE} --label prio:P1 --body-file <body>"], self.calls)

    def test_without_a_report_it_says_so_and_how_the_run_ended(self):
        self.assertEqual(0, self.report(REPORT=self.path("missing.json"), RESULT="cancelled"))
        self.assertEqual(
            RED_HEADING + "La ejecución terminó en `cancelled` sin informe de las pruebas: lo que falló está antes o"
            " fuera de las specs (preparación, servidores, tiempo agotado). El log del run lo dice.\n",
            self.summary,
        )
        self.assertEqual([SEARCH, f"gh issue create --title {TITLE} --label prio:P1 --body-file <body>"], self.calls)

    def test_a_run_stopped_in_global_setup_lists_its_own_error(self):
        self.assertEqual(0, self.report(REPORT=self.write("setup.json", SETUP)))
        self.assertEqual(
            RED_HEADING + "0 en rojo · 0 bien · 0 saltadas\n\n- Error de la ejecución: Error: unapplied migrations"
            " (hubs.0042)\n",
            self.summary,
        )

    def test_a_red_end_with_no_red_test_in_the_report_points_at_the_log(self):
        green = self.write("green.json", suite_of(spec("ok", 1, [{"projectName": "panel", "status": "expected"}])))
        self.assertEqual(0, self.report(REPORT=green, RESULT="timed_out"))
        self.assertEqual(
            RED_HEADING + "1 en rojo · 1 bien · 0 saltadas\n\n\nEl informe no tiene ninguna prueba en rojo, pero la"
            " ejecución terminó en `timed_out`: el log del run dice por qué.\n",
            self.summary,
        )

    def test_outside_main_only_the_summary_is_written(self):
        for publish in ("false", None, "", "TRUE"):
            with self.subTest(PUBLISH=publish):
                self.assertEqual(0, self.report(PUBLISH=publish, OPEN_ISSUES=OPEN))
                self.assertEqual([], self.calls)
                self.assertEqual(RED_HEADING + RED_DETAILS + "\nFuera de main: no se escribe ninguna issue.\n",
                                 self.summary)


class GreenNightTest(NightCase):
    def test_a_green_run_closes_the_open_issue_with_the_run(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=OPEN, RESULT="success", REPORT=self.path("missing.json")))
        closing = f"La pasada del 2026-11-06 ha salido entera en verde: {RUN} (commit `0123456`). Se cierra."
        self.assertEqual([SEARCH, f"gh issue close 42 --reason completed --comment {closing}"], self.calls)
        self.assertEqual(closing + "\n", self.bodies)
        self.assertEqual(GREEN_SUMMARY, self.summary)

    def test_a_green_run_with_no_open_issue_writes_none(self):
        self.assertEqual(0, self.report(RESULT="success", REPORT=self.path("missing.json")))
        self.assertEqual([SEARCH], self.calls)
        self.assertEqual(GREEN_SUMMARY, self.summary)

    def test_outside_main_a_green_run_only_writes_its_summary(self):
        self.assertEqual(0, self.report(OPEN_ISSUES=OPEN, RESULT="success", PUBLISH="false"))
        self.assertEqual([], self.calls)
        self.assertEqual(GREEN_SUMMARY, self.summary)


class FailureTest(NightCase):
    def test_a_gh_that_fails_fails_the_report_with_its_exit_code(self):
        cases = [
            ({"GH_FAILS": "1"}, 1, [SEARCH]),
            ({"GH_FAILS": "4"}, 4, [SEARCH]),
            ({"GH_FAILS": "3", "RESULT": "success", "OPEN_ISSUES": OPEN}, 3, [SEARCH]),
            ({"GH_FAILS": "7", "GH_FAILS_ON": "issue create"}, 7, [SEARCH, f"gh issue create --title {TITLE} --label"
                                                                           " prio:P1 --body-file <body>"]),
            ({"GH_FAILS": "8", "GH_FAILS_ON": "issue comment", "OPEN_ISSUES": OPEN}, 8,
             [SEARCH, "gh issue comment 42 --body-file <body>"]),
            ({"GH_FAILS": "6", "GH_FAILS_ON": "issue close", "OPEN_ISSUES": OPEN, "RESULT": "success"}, 6, None),
        ]
        for settings, code, calls in cases:
            with self.subTest(**settings):
                self.assertEqual(code, self.report(**settings))
                self.assertIn("HTTP 502", self.stderr)
                if calls is not None:
                    self.assertEqual(calls, self.calls)

    def test_an_answer_of_gh_that_is_no_list_of_issues_stops_the_report(self):
        for answer in ("not json", "5", "[5]"):
            with self.subTest(answer=answer):
                self.assertEqual(5, self.report(OPEN_ISSUES=answer))
                self.assertEqual([SEARCH], self.calls)

    def test_a_missing_or_empty_setting_stops_it_before_anything(self):
        for name in SETTINGS:
            for value in (None, ""):
                with self.subTest(setting=name, value=value):
                    self.assertEqual(1, self.report(**{name: value}))
                    self.assertIn(name, self.stderr)
                    self.assertEqual(([], ""), (self.calls, self.summary))

    def test_a_report_it_cannot_read_through_stops_it_before_the_summary(self):
        for result in ("failure", "success"):
            with self.subTest(RESULT=result):
                self.assertEqual(5, self.report(REPORT=self.write("array.json", "[]"), RESULT=result))
                self.assertEqual(([], ""), (self.calls, self.summary))
                self.assertIn("stats", self.stderr)


class DefaultsTest(NightCase):
    def test_the_night_is_today_in_utc_unless_given(self):
        before = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        for day in (None, ""):
            with self.subTest(DAY=day):
                self.assertEqual(0, self.report(DAY=day, RESULT="success"))
                after = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                self.assertTrue(any(f"La pasada del {date} ha salido" in self.summary for date in (before, after)))

    def test_without_a_step_summary_it_still_reports(self):
        for summary in (None, ""):
            with self.subTest(GITHUB_STEP_SUMMARY=summary):
                self.assertEqual(0, self.report(GITHUB_STEP_SUMMARY=summary, OPEN_ISSUES=OPEN))
                self.assertEqual([SEARCH, "gh issue comment 42 --body-file <body>"], self.calls)

    def test_the_summary_is_added_to_what_the_step_already_wrote(self):
        earlier = self.write("earlier.md", "earlier\n")
        self.assertEqual(0, self.report(GITHUB_STEP_SUMMARY=earlier, RESULT="success"))
        self.assertEqual("earlier\n" + GREEN_SUMMARY, self.read("earlier.md"))


class NewestIssueTest(unittest.TestCase):
    def test_it_is_the_highest_number_among_the_issues_of_exactly_that_title(self):
        def issues(*numbers, title=TITLE):
            return json.dumps([{"number": number, "title": title} for number in numbers])

        cases = [
            ("", ""), ("[]", ""), (issues(7, title=TITLE + " (otra)"), ""), (issues(42, 44), "44"),
            (json.dumps({"a": {"number": 7, "title": TITLE}}), "7"), (issues(0), "0"), (issues(False), ""),
            (issues(None), ""), (issues(3) + "\n" + issues(5), "3\n5"),
        ]
        for answer, number in cases:
            with self.subTest(answer=answer):
                self.assertEqual(number, e2e_report.newest_issue(answer))


class ReadingTest(unittest.TestCase):
    """What the report lists, read from Playwright's JSON with jq's rules."""

    def details(self, *documents, result="failure"):
        return e2e_report.details(result, list(documents))

    def listed(self, test):
        return self.details(lines_of(test)).splitlines()[2]

    def test_a_message_keeps_its_first_line_without_colours_cut_at_200_characters(self):
        long = "ñ" * 150 + "\x1b[31m" + "🙂" * 100 + "\nnext"
        self.assertEqual("- `[panel] a.spec.ts:1` › t — " + "ñ" * 150 + "🙂" * 50, self.listed(red(error(long))))
        self.assertTrue(self.listed(red(error("a\x1b[1;31mb\x1b[Kc\x1b[mz"))).endswith(" — ab\x1b[Kcz"))

    def test_a_red_test_with_no_message_left_is_written_with_null(self):
        for test in (red(), {**red(), "results": []}, red(error("first"), None), red(error("first"), {}),
                     red(error(None)), red(error(False)), red(error("")), red(error("\x1b[31m\x1b[0m"))):
            with self.subTest(test=test):
                self.assertEqual("- `[panel] a.spec.ts:1` › t — null", self.listed(test))

    def test_a_message_whose_first_line_is_empty_gets_no_suffix(self):
        self.assertEqual("- `[panel] a.spec.ts:1` › t", self.listed(red(error("\nsecond"))))

    def test_only_the_last_result_counts(self):
        self.assertTrue(self.listed(red(error("first"), error("last"))).endswith("› t — last"))

    def test_specs_come_before_the_describes_inside_them_and_the_file_title_is_left_out(self):
        nested = {"suites": [{
            "title": "top", "file": "f",
            "suites": [{"title": "d1", "specs": [spec("in d1", 5, [red(error("e1"))])],
                        "suites": [{"title": "d2", "specs": [spec("in d2", 6, [red(error("e2"))])]}]}],
            "specs": [spec("top spec", 2, [red(error("e0"))])],
        }], "stats": STATS}
        self.assertEqual(
            ["- `[panel] a.spec.ts:2` › top spec — e0", "- `[panel] a.spec.ts:5` › d1 › in d1 — e1",
             "- `[panel] a.spec.ts:6` › d1 › d2 › in d2 — e2"],
            self.details(nested).splitlines()[2:],
        )

    def test_any_value_is_written_as_jq_writes_it(self):
        odd = {"suites": [{"title": "s", "suites": [{"title": None, "suites": [{"title": 7, "suites": [{
            "title": True,
            "specs": [{"title": 1.5, "file": None, "line": "L", "tests": [red(error("m"), project=None)]}],
        }]}]}]}], "stats": {"unexpected": {"a": [1, "ñ"]}, "expected": 2.0, "skipped": None}}
        self.assertEqual(
            ['{"a":[1,"ñ"]} en rojo · 2.0 bien · null saltadas', "", "- `[null] null:L` ›  › 7 › true › 1.5 — m"],
            self.details(odd).splitlines(),
        )
        self.assertEqual("- `[null] a.spec.ts:1` › t — m", self.listed({"status": "unexpected", "results": [error("m")]}))
        self.assertEqual("null en rojo · null bien · null saltadas\n\n", self.details({"stats": None}, result="success"))

    def test_a_run_error_without_a_message_is_written_as_null(self):
        for errors in ([{}], [None], [{"message": ""}], [{"message": None}]):
            with self.subTest(errors=errors):
                self.assertIn("\n- Error de la ejecución: null\n", self.details({"errors": errors, "stats": STATS}))

    def test_lists_may_be_objects_and_anything_else_lists_nothing(self):
        as_objects = {"suites": {"x": {"title": "x", "specs": {"s": spec("o", 3, {"k": red(error("m"))})}}},
                      "errors": {"e": {"message": "from an object"}}, "stats": STATS}
        self.assertEqual(["- `[panel] a.spec.ts:3` › o — m", "- Error de la ejecución: from an object"],
                         self.details(as_objects).splitlines()[2:])
        nothing = {"suites": [{"title": "s", "specs": 5, "suites": "x"}], "errors": 5, "stats": STATS}
        self.assertEqual(["1 en rojo · 1 bien · 0 saltadas", ""], self.details(nothing).splitlines()[:2])

    def test_a_line_starting_with_a_dash_anywhere_counts_as_a_listed_failure(self):
        dashed = {"stats": {"unexpected": "a\n- b", "expected": 0, "skipped": 0}}
        self.assertEqual("a\n- b en rojo · 0 bien · 0 saltadas\n\n", self.details(dashed))

    def test_each_json_document_of_the_report_is_read(self):
        self.assertEqual(
            [
                "0 en rojo · 0 bien · 0 saltadas",
                "2 en rojo · 1 bien · 1 saltadas",
                "",
                "- Error de la ejecución: Error: unapplied migrations (hubs.0042)",
                *RED_DETAILS.splitlines()[2:],
            ],
            self.details(SETUP, RED).splitlines(),
        )

    def test_what_jq_could_not_read_through_stops_the_report(self):
        refused = [
            [], "x", 5, True, {"stats": "x"}, suite_of({"title": "t", "file": "f", "line": 1}),
            suite_of(spec("t", 1, None)), suite_of(spec("t", 1, "x")), suite_of(None), suite_of(5),
            {"suites": [5], "stats": STATS}, {"suites": [{"title": "s", "suites": ["x"]}], "stats": STATS},
            suite_of(spec(["a"], 1, [red(error("m"))])), suite_of(spec({"a": 1}, 1, [red(error("m"))])),
            lines_of(red(error(5))), lines_of(red(error(0))), lines_of({**red(), "results": {"a": 1}}),
            lines_of({**red(), "results": "abc"}), lines_of(red({"error": "boom"})), lines_of(5),
            {"errors": ["x"], "stats": STATS}, lines_of(red(5)),
        ]
        for document in refused:
            with self.subTest(document=document), self.assertRaises(e2e_report.Refused) as refusal:
                self.details(document)
            self.assertEqual(5, refusal.exception.code)


class ReadReportTest(unittest.TestCase):
    def read(self, content):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text(content, encoding="utf-8")
            return e2e_report.read_report(str(path))

    def test_no_readable_report_is_no_report(self):
        for content in ("", "  \n\t ", "{not json", "null", "false", "{} null", "{} x"):
            with self.subTest(content=content):
                self.assertIsNone(self.read(content))
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(e2e_report.read_report(folder))
            self.assertIsNone(e2e_report.read_report(str(Path(folder) / "missing.json")))

    def test_a_report_is_read_as_its_json_documents(self):
        self.assertEqual([{"a": 1}], self.read('{"a": 1}'))
        self.assertEqual([{}, []], self.read(" {}\n[] \n"))
        self.assertEqual([True], self.read("true"))


if __name__ == "__main__":
    unittest.main()
