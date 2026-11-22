"""Tests of ecs_common.py, what the saas's deploy and rollback share, and the way their tests run them.

    python3 -m unittest discover -s .github/scripts -p '*_test.py'

How each script uses these pieces with a fake aws CLI is tested by ecs_deploy*_test.py and ecs_rollback*_test.py.
Only the standard library.
"""

from __future__ import annotations

import io
import json
import re
import signal
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import ecs_common

# Runs a script as `python3 <script>` runs it (its folder first on sys.path), except that time.sleep only records the
# pause, so no test waits for real, and gives up after 500 of them, so a loop that never times out fails its test
# instead of hanging.
BOOT = """\
import os, runpy, sys, time

def sleep(seconds):
    with open(os.environ["SLEEP_LOG"], "a", encoding="utf-8") as log:
        log.write(f"{seconds}\\n")
    with open(os.environ["SLEEP_LOG"], encoding="utf-8") as log:
        if len(log.readlines()) > 500:
            sys.exit("fake sleep: more than 500 pauses")

time.sleep = sleep
sys.path[0] = os.path.dirname(os.path.abspath(sys.argv[1]))
runpy.run_path(sys.argv[1], run_name="__main__")
"""


def run_script(script: Path, cwd: Path, env: dict, apart: bool) -> subprocess.CompletedProcess:
    """Runs <script> with BOOT; stdout and stderr land together in stdout, or apart."""
    return subprocess.run([sys.executable, "-c", BOOT, str(script)], cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE if apart else subprocess.STDOUT, timeout=120, check=False)


class ScriptCase(unittest.TestCase):
    """What the tests of the deploy and of the rollback read of a run: its output and exit code, the aws calls its fake
    recorded in <work>/calls.log and the pauses in <work>/sleep.log. A subclass sets self.work in setUp, and
    cluster_scoped: the ecs calls that act in a cluster."""

    cluster_scoped: re.Pattern

    def execute(self, script: Path, cwd: Path, environ: dict, apart: bool) -> int:
        """Runs <script>: stdout and stderr land together in self.out, or apart in self.stdout and self.stderr."""
        done = run_script(script, cwd, environ, apart)
        self.stdout, self.stderr = done.stdout, done.stderr
        self.out = done.stdout.decode("utf-8", "replace")
        self.status = done.returncode
        return done.returncode

    def calls(self) -> list[str]:
        return (self.work / "calls.log").read_text(errors="replace").splitlines()

    def lines(self, pattern: str) -> list[int]:
        return [n for n, call in enumerate(self.calls(), 1) if re.search(pattern, call)]

    def line_of(self, pattern: str) -> int:
        return self.lines(pattern)[0]

    def last_line_of(self, pattern: str) -> int:
        return self.lines(pattern)[-1]

    def called(self, pattern: str) -> bool:
        return bool(self.lines(pattern))

    def pauses(self) -> list[str]:
        return (self.work / "sleep.log").read_text().split()

    def cluster_is(self, cluster: str) -> bool:
        """There are cluster-scoped ecs calls, and every call that names a cluster names <cluster>."""
        named = [call for call in self.calls() if "--cluster" in call]
        return any(self.cluster_scoped.search(call) for call in self.calls()) and all(
            f"--cluster {cluster} " in call for call in named)

    def assertFailsBeforeAnyCall(self, *said: str):
        self.assertNotEqual(0, self.status)
        self.assertEqual([], self.calls())
        for line in said:
            self.assertIn(line, self.out)


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class RunTest(unittest.TestCase):
    def test_what_a_command_writes_comes_back_without_its_trailing_newlines(self):
        self.assertEqual("a\udcff \n b", ecs_common.run(python(
            "import sys; sys.stdout.buffer.write(b'a\\xff \\n b\\n\\n')")))
        self.assertEqual("", ecs_common.run(python("pass"), stdout=subprocess.DEVNULL))

    def test_a_command_reads_what_it_is_given(self):
        self.assertEqual("ñ", ecs_common.run(python("import sys; print(sys.stdin.read())"), stdin="ñ".encode()))

    def test_a_command_that_fails_stops_with_its_code(self):
        with self.assertRaises(ecs_common.Stop) as stopped:
            ecs_common.run(python("import sys; sys.exit(3)"))
        self.assertEqual(3, stopped.exception.code)

    def test_a_command_killed_by_a_signal_stops_with_128_plus_the_signal(self):
        with self.assertRaises(ecs_common.Stop) as stopped:
            ecs_common.run(python(f"import os; os.kill(os.getpid(), {int(signal.SIGKILL)})"))
        self.assertEqual(137, stopped.exception.code)

    def test_a_command_that_does_not_exist_stops_with_127_named_by_the_script(self):
        said = io.StringIO()
        with mock.patch.object(sys, "argv", ["/somewhere/ecs_rollback.py"]), redirect_stderr(said), \
                self.assertRaises(ecs_common.Stop) as stopped:
            ecs_common.run(["no-such-command-here", "x"])
        self.assertEqual(127, stopped.exception.code)
        self.assertEqual("ecs_rollback.py: no-such-command-here: command not found\n", said.getvalue())

    def test_a_refusal_says_its_error_and_stops_with_1(self):
        said = io.StringIO()
        with redirect_stderr(said):
            stop = ecs_common.refusal("no")
        self.assertEqual((1, "::error::no\n"), (stop.code, said.getvalue()))
        with redirect_stderr(said):
            stop = ecs_common.unreadable("the answer", ValueError("bad"))
        self.assertEqual(ecs_common.UNREADABLE, stop.code)
        self.assertTrue(said.getvalue().endswith(": the answer cannot be read: bad\n"), said.getvalue())


class SettingsTest(unittest.TestCase):
    def refused(self, call) -> str:
        said = io.StringIO()
        with redirect_stderr(said), self.assertRaises(ecs_common.Stop) as stopped:
            call()
        self.assertEqual(1, stopped.exception.code)
        return said.getvalue()

    def test_the_environment_is_prod_or_pre(self):
        for environment in ("prod", "pre"):
            self.assertEqual(environment, ecs_common.environment_given({"ENVIRONMENT": environment}, "; x"))
        for env in ({}, {"ENVIRONMENT": "Prod"}, {"ENVIRONMENT": "prod "}):
            said = self.refused(lambda env=env: ecs_common.environment_given(env, "; x"))
            self.assertEqual(f"::error::ENVIRONMENT must be prod or pre, not '{env.get('ENVIRONMENT', '')}'; x\n",
                             said)

    def test_the_seconds_are_digits_as_given_or_their_default(self):
        defaults = {"A": "15", "B": "600"}
        self.assertEqual({"A": "007", "B": "600"}, ecs_common.seconds_given({"A": "007", "B": ""}, defaults, ""))
        for value in ("soon", "1.5", "-1", " 1", "1\n", "١", "+5"):
            said = self.refused(lambda value=value: ecs_common.seconds_given({"B": value}, defaults, "; y"))
            self.assertEqual(f"::error::B must be a number of seconds, not '{value}'; y\n", said)

    def test_a_release_names_its_environment(self):
        release = ecs_common.Release(region="r", environment="pre", cluster="c", seconds={"A": "010"})
        self.assertEqual((False, "-pre", "erplora-pre", 10), (release.prod, release.suffix, release.prefix,
                                                             release.seconds_of("A")))
        prod = ecs_common.Release(region="r", environment="prod", cluster="c", seconds={})
        self.assertEqual((True, "", "erplora-prod"), (prod.prod, prod.suffix, prod.prefix))


class ReadingTest(unittest.TestCase):
    def test_the_arns_listed_are_the_words_of_the_first_line(self):
        self.assertEqual(["a:1", "b:2\x0bc"], ecs_common.arns_listed(" \ta:1 \t b:2\x0bc\t\nd:3"))
        self.assertEqual([], ecs_common.arns_listed(""))

    def test_only_the_family_itself_counts(self):
        family = "erplora-prod-saas-worker"
        for listed, own in ((f"arn:td/{family}-longer:3\tarn:td/{family}:1", True), (f"/{family}", True),
                            (f"arn:td/{family}:1:2", False), (f"None\narn:td/{family}:1", False),
                            (f"arn:td/other-{family}:1", False), (f"arn:td/{family}x:1", False), ("", False)):
            self.assertEqual(own, ecs_common.own_family_listed(listed, family), listed)

    def test_a_key_is_read_as_jq_reads_it(self):
        self.assertEqual((None, 1, None), (ecs_common.key(None, "a"), ecs_common.key({"a": 1}, "a"),
                                           ecs_common.key({}, "a")))
        for value in ([1], "s", 1, True):
            with self.assertRaises(TypeError):
                ecs_common.key(value, "a")

    def test_the_tags_are_read_as_jq_reads_them(self):
        tag = {"key": "Environment", "value": "pre"}
        for tags in ([None, tag], [tag, "x"], {"one": tag}):
            self.assertTrue(ecs_common.tagged({"tags": tags}, "pre"), tags)
        for tags in (["x", tag], [1, tag], "pre", [], None, [{"key": "Environment"}], [{"key": "Stage", "value": "pre"}]):
            self.assertFalse(ecs_common.tagged({"tags": tags}, "pre"), tags)
        self.assertFalse(ecs_common.tagged({}, "pre"))

    def test_a_revision_of_its_environment_has_its_tag_and_its_roles(self):
        role = "arn:aws:iam::123456789012:role/erplora-pre-saas"
        found = {"taskDefinition": {"taskRoleArn": f"{role}-task", "executionRoleArn": f"{role}-execution"},
                 "tags": [None, {"key": "Environment", "value": "pre"}, "x"]}
        self.assertTrue(ecs_common.of_its_environment(json.dumps(found), "pre"))
        self.assertFalse(ecs_common.of_its_environment(json.dumps(found), "prod"))
        for broken in ("", "[]", "{} {}", '{"tags": [{"key": "Environment", "value": "pre"}]}'):
            self.assertFalse(ecs_common.of_its_environment(broken, "pre"), broken)


class MainTest(unittest.TestCase):
    def test_the_work_ends_with_its_code(self):
        def stops():
            raise ecs_common.Stop(254)

        with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO())), \
                mock.patch.object(sys, "stderr", io.TextIOWrapper(io.BytesIO())):
            self.assertEqual((254, 0), (ecs_common.main(stops), ecs_common.main(lambda: None)))
            self.assertEqual(("utf-8", "surrogateescape", True),
                             (sys.stdout.encoding, sys.stderr.errors, sys.stdout.line_buffering))


if __name__ == "__main__":
    unittest.main()
