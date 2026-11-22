#!/usr/bin/env python3
"""The report of the nightly e2e run (nightly.yml): lists what came out red, from Playwright's JSON report, in the
run's summary, and on main keeps ONE open issue about it: a red night opens it (or comments on it when it is already
open) and the first green night closes it.

  RESULT=<e2e job's result> REPORT=<json report> RUN_URL=<run> SHA=<commit> PUBLISH=true|false \
    GH_REPO=<owner/repo> GH_TOKEN=<token> python3 .github/scripts/e2e_report.py

Every result other than `success` is red (a timeout or a cancel included). A missing report is said, not hidden: the
run stopped before or outside the specs. Only PUBLISH=true writes issues (main); elsewhere the summary is all. A gh
call that fails fails the step with gh's exit code. Optional: DAY (the night's date, default today in UTC) and
GITHUB_STEP_SUMMARY.

The report is read with jq's rules, which the summary and the issue keep: a value is written as jq writes it (null,
numbers, objects as compact JSON), a list may also be an object, and a value jq could not index or iterate stops the
report with jq's exit code, 5. Only the standard library: the workflow runs it with the runner's python3.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TITLE = "Pruebas de navegador del SaaS en rojo en la pasada nocturna"
SETTINGS = ("RESULT", "REPORT", "RUN_URL", "SHA")
REFUSED = 5
COLOUR = re.compile(r"\x1b\[[0-9;]*m")
BLANK = re.compile(r"[ \t\n\r]*")

NO_REPORT = (
    "La ejecución terminó en `{result}` sin informe de las pruebas: lo que falló está antes o fuera de las specs"
    " (preparación, servidores, tiempo agotado). El log del run lo dice.\n"
)
NOTHING_RED = (
    "\nEl informe no tiene ninguna prueba en rojo, pero la ejecución terminó en `{result}`: el log del run dice por"
    " qué.\n"
)
ISSUE_OPENING = (
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
    "- Pasada del {day}: {run_url} (commit `{commit}`). Las trazas y capturas de cada fallo, en su artefacto"
    " `e2e-test-results`.\n"
    "- Se repite una prueba desde `saas/` con `pnpm e2e:ci <spec>` (`tests/e2e/README.md`).\n"
    "\n"
)
ISSUE_CLOSING = (
    "\n"
    "## Origen\n"
    "- Cómo se llegó: la pasada nocturna de las pruebas de navegador (`.github/workflows/nightly.yml`).\n"
    "- Sale de #296\n"
    "- La introdujo una PR: no comprobado — la pasada no sabe qué cambio la rompió; se busca entre los commits desde"
    " la última noche en verde.\n"
    "\n"
    "## Cómo se reproduce\n"
    "- Run: {run_url}\n"
    "\n"
    "## Flujo\n"
    "- Flujo: ninguno — la pasada no sabe qué flujo prueba cada spec; el triaje lo pone al leerla.\n"
)


class Refused(Exception):
    """Stops the report with an exit code: a value jq could not read through, or a gh call that failed."""

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Night:
    result: str
    run_url: str
    commit: str
    day: str
    publish: bool
    summary: str


def field(value, key: str):
    """jq's `.key`: null on null and for a missing key; anything but an object or null is refused."""
    if isinstance(value, dict):
        return value.get(key)
    if value is None:
        return None
    raise Refused(REFUSED, f"cannot index {type(value).__name__} with {key!r}")


def each(value) -> list:
    """jq's `.[]`: the items of a list or the values of an object; anything else is refused."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    raise Refused(REFUSED, f"cannot iterate over {type(value).__name__}")


def each_if_any(value) -> list:
    """jq's `.[]?`: like each, with nothing for what cannot be iterated."""
    return each(value) if isinstance(value, (list, dict)) else []


def last(value):
    """jq's `last`: the last item of a list, null for an empty one or for null; anything else is refused."""
    if isinstance(value, list):
        return value[-1] if value else None
    if value is None:
        return None
    raise Refused(REFUSED, f"cannot index {type(value).__name__} with a number")


def or_empty(value):
    """jq's `// ""`."""
    return "" if value is None or value is False else value


def text(value) -> str:
    """A value inside a jq string: a string as it is, anything else as compact JSON."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def joined(titles: list) -> str:
    """jq's `join(" › ")`: null as nothing, numbers and booleans as JSON; a list or an object is refused."""
    for title in titles:
        if isinstance(title, (list, dict)):
            raise Refused(REFUSED, f"cannot join a {type(title).__name__}")
    return " › ".join("" if title is None else text(title) for title in titles)


def plain(message):
    """The first line of a message without colour codes, cut at 200 characters; null when nothing is left."""
    if not isinstance(message, str):
        raise Refused(REFUSED, f"{type(message).__name__} cannot be matched, as it is not a string")
    message = COLOUR.sub("", message)
    return message.split("\n")[0][:200] if message else None


def specs(suite, path: list):
    """Each spec of a suite and of the describes inside it, with the titles that lead to it."""
    for spec in each_if_any(field(suite, "specs")):
        yield [*path, field(spec, "title")], spec
    for child in each_if_any(field(suite, "suites")):
        yield from specs(child, [*path, field(child, "title")])


def tests(report):
    """Each test of a report, with its spec and the titles that lead to it; a file's own title is left out."""
    for suite in each_if_any(field(report, "suites")):
        for path, spec in specs(suite, []):
            for test in each(field(spec, "tests")):
                yield path, spec, test


def red_line(path: list, spec, test) -> str | None:
    """The markdown line of a test that came out red, with the first line of its error; None for any other test."""
    if field(test, "status") != "unexpected":
        return None
    message = plain(or_empty(field(field(last(field(test, "results")), "error"), "message")))
    where = f"[{text(field(test, 'projectName'))}] {text(field(spec, 'file'))}:{text(field(spec, 'line'))}"
    line = f"- `{where}` › {joined(path)}"
    return line if message == "" else f"{line} — {text(message)}"


def red_lines(report) -> list[str]:
    """The red tests of a report and the run's own errors, one markdown line each."""
    lines = [line for line in (red_line(*found) for found in tests(report)) if line is not None]
    errors = each_if_any(field(report, "errors"))
    return lines + [f"- Error de la ejecución: {text(plain(or_empty(field(error, 'message'))))}" for error in errors]


def counts(report) -> str:
    stats = field(report, "stats")
    red, passed, skipped = (text(field(stats, key)) for key in ("unexpected", "expected", "skipped"))
    return f"{red} en rojo · {passed} bien · {skipped} saltadas"


def details(result: str, documents: list | None) -> str:
    """What came out red, for the summary and the issue: the counts and a line per failure, or why there are none."""
    if documents is None:
        return NO_REPORT.format(result=result)
    found = "".join(f"{counts(document)}\n" for document in documents) + "\n"
    found += "".join(f"{line}\n" for document in documents for line in red_lines(document))
    if result != "success" and not any(line.startswith("- ") for line in found.split("\n")):
        found += NOTHING_RED.format(result=result)
    return found


def documents_of(raw: str) -> list:
    """The JSON documents of a text, one after another; ValueError when one of them is no JSON."""
    decoder = json.JSONDecoder()
    found = []
    at = BLANK.match(raw).end()
    while at < len(raw):
        document, at = decoder.raw_decode(raw, at)
        found.append(document)
        at = BLANK.match(raw, at).end()
    return found


def read_report(path: str) -> list | None:
    """The report's JSON documents; None when there is none to read: missing, empty, no JSON, or ending in null or
    false."""
    try:
        documents = documents_of(Path(path).read_bytes().decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if not documents or documents[-1] is None or documents[-1] is False:
        return None
    return documents


def newest_issue(answer: str) -> str:
    """The number of the newest open issue of exactly TITLE in gh's answer, or "" when there is none."""
    try:
        documents = documents_of(answer)
    except ValueError as error:
        raise Refused(REFUSED, f"gh's answer is no JSON: {error}") from error
    newest = []
    for document in documents:
        number = max((field(issue, "number") for issue in each(document) if field(issue, "title") == TITLE),
                     default=None)
        if number is not None and number is not False:
            newest.append(text(number))
    return "\n".join(newest)


def open_issue() -> str:
    """The open issue of exactly that title: searched by its title, never among the latest issues, where a busy
    repo would bury it and a second one would be opened."""
    search = ["issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title', "--limit", "50"]
    answer = subprocess.run(["gh", *search, "--json", "number,title"], stdout=subprocess.PIPE, check=False)
    number = newest_issue(answer.stdout.decode("utf-8", errors="replace"))
    if answer.returncode != 0:
        raise Refused(answer.returncode)
    return number


def gh(*args: str) -> None:
    """A gh call that writes an issue; its output is the step's, and its failure fails the step."""
    done = subprocess.run(["gh", *args], check=False)
    if done.returncode != 0:
        raise Refused(done.returncode)


def gh_with_body(args: list[str], body: str) -> None:
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "body.md"
        path.write_text(body, encoding="utf-8")
        gh(*args, "--body-file", str(path))


def append(path: str, content: str) -> None:
    with open(path, "a", encoding="utf-8") as summary:
        summary.write(content)


def green(night: Night) -> None:
    append(night.summary, f"## Pruebas de navegador: en verde\n\nLa pasada del {night.day} ha salido en verde:"
                          f" {night.run_url}\n")
    if not night.publish:
        return
    number = open_issue()
    if number:
        closing = f"La pasada del {night.day} ha salido entera en verde: {night.run_url} (commit `{night.commit}`)."
        gh("issue", "close", number, "--reason", "completed", "--comment", f"{closing} Se cierra.")


def red(night: Night, found: str) -> None:
    summary = f"## Pruebas de navegador: en rojo\n\n{night.run_url} (commit `{night.commit}`)\n\n{found}"
    if not night.publish:
        summary += "\nFuera de main: no se escribe ninguna issue.\n"
    append(night.summary, summary)
    if not night.publish:
        return
    number = open_issue()
    if number:
        still = f"La pasada del {night.day} sigue en rojo: {night.run_url} (commit `{night.commit}`).\n\n"
        gh_with_body(["issue", "comment", number], still + found)
        return
    opening = ISSUE_OPENING.format(day=night.day, run_url=night.run_url, commit=night.commit)
    body = opening + found + ISSUE_CLOSING.format(run_url=night.run_url)
    gh_with_body(["issue", "create", "--title", TITLE, "--label", "prio:P1"], body)


def main() -> int:
    env = os.environ
    for name in SETTINGS:
        if not env.get(name):
            print(f"e2e_report.py: {name}: parameter null or not set", file=sys.stderr)
            return 1
    night = Night(
        result=env["RESULT"],
        run_url=env["RUN_URL"],
        commit=env["SHA"][:7],
        day=env.get("DAY") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
        publish=env.get("PUBLISH") == "true",
        summary=env.get("GITHUB_STEP_SUMMARY") or os.devnull,
    )
    try:
        found = details(night.result, read_report(env["REPORT"]))
        if night.result == "success":
            green(night)
        else:
            red(night, found)
    except Refused as refusal:
        if str(refusal):
            print(f"e2e_report.py: {refusal}", file=sys.stderr)
        return refusal.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
