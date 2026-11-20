"""What the store publishes of an app's user documentation, from the markdown the Hub registers.

The Hub registers the customer's part of each WORKBOOK as written. Of each flow the store publishes what
the Hub's help window does: only the flows that are done, each with its title without its id, its steps
and what happens if it fails; the flow keys are read in the document's language with the Hub's words.
The index table of the flows leaves. A flow id left in the text becomes the «title» of that flow when it
is published; any other flow id and every issue number point at nothing a reader can open, so between
parentheses the part of the enumeration that holds one leaves, and elsewhere the reference alone. In a
published flow, a part between parentheses that names an operation, an event or an error leaves too, and
so does a clause that holds a size in pixels. Code blocks stay as written.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import groupby
from operator import itemgetter


@dataclass(frozen=True)
class Words:
    """How a WORKBOOK in one language writes a flow's keys and a flow that is done."""

    done: str
    status: str
    steps: str
    failure: str
    keys: tuple[str, ...]


WORDS = {
    "es": Words(
        done="hecho",
        status="Estado",
        steps="Pasos",
        failure="Si falla",
        keys=("Estado", "Vertical", "Actor", "Pantalla", "Pasos", "Entra", "Sale", "Si falla",
              "Por el asistente", "Implicados"),
    ),
    "en": Words(
        done="done",
        status="Status",
        steps="Steps",
        failure="If it fails",
        keys=("Status", "Vertical", "Actor", "Screen", "Steps", "In", "Out", "If it fails",
              "Through the assistant", "Involved"),
    ),
}

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}#{1,3}(?:\s|$)")
_FLOW = re.compile(r"^### ([A-Z][A-Z0-9_]*-F\d+)\s+(.+)$")
_TABLE_ROW = re.compile(r"^ {0,3}\|")
_FLOW_ID = r"\b[A-Z][A-Z0-9_]*-F\d+\b"
#: A flow of the same app by its number alone (F05); one digit is an invoice type (F1, F2, F3).
_SHORT_FLOW_ID = r"(?<![\w-])F\d{2,3}\b"
_ISSUE = r"(?<![\w/.-])[\w.-]+(?:/[\w.-]+)?#\d+\b"
_REFERENCE = re.compile(rf"{_FLOW_ID}|{_SHORT_FLOW_ID}|{_ISSUE}")
_PIXELS = re.compile(r"\b\d+ ?px\b")
#: An operation's, event's or error's name in code, dotted or with an underscore and in lower case
#: (table.zone.created, service_unavailable). A value the reader types, like {{1}} or
#: OS-AAAAMMDD-NNNN, does not look like one and stays.
_CODE_NAME = re.compile(r"`[.*_]*[a-z][a-z0-9*]*[._][a-z0-9_.*]*`")
#: What is left around a part that leaves a parenthesis, or a line it wraps.
_SEPARATORS = " \t\n,"
_PARENTHESIS = re.compile(r"[ \t]*\(([^()]*)\)")
_SPACE_BEFORE_MARK = re.compile(r"(?<=\S)[ \t]+(?=[.,;:)](?:\s|$))")
_DOUBLE_SPACE = re.compile(r"(?<=\S)[ \t]{2,}(?=\S)")


@dataclass
class _Block:
    lines: list[str]
    code: bool = False
    #: A published flow's id and title; empty for any other block.
    flow_id: str = ""
    title: str = ""


def public_markdown(markdown: str, language: str) -> str:
    """The markdown the store paints of a document written in ``language``."""
    blocks = list(_blocks(markdown.splitlines(), WORDS[language]))
    titles = _titles(blocks)
    out: list[str] = []
    for block in blocks:
        if block.code:
            out.extend(block.lines)
            continue
        for line in _clean(block.lines, titles, strict=bool(block.flow_id)):
            if line.strip() or (out and out[-1].strip()):
                out.append(line)
    return "\n".join(_trimmed(out)) + "\n"


def _titles(blocks: list[_Block]) -> dict[str, str]:
    """The title of each published flow by its id and, when no other flow shares it, by its number alone."""
    titles = {block.flow_id: block.title for block in blocks if block.flow_id}
    numbers: dict[str, list[str]] = {}
    for flow_id, title in titles.items():
        numbers.setdefault(flow_id.rsplit("-", 1)[1], []).append(title)
    return titles | {number: found[0] for number, found in numbers.items() if len(found) == 1}


def _blocks(lines: list[str], words: Words) -> Iterator[_Block]:
    """The document cut into code blocks, published flows and the text around them, in order."""
    for section in _sections(_tagged(lines)):
        first, code = section[0]
        heading = None if code else _FLOW.match(first)
        if heading:
            body = [line for line, _code in section[1:]]
            yield _flow(heading.group(1), heading.group(2).strip(), body, words)
            continue
        for code, run in groupby(section, key=itemgetter(1)):
            run_lines = [line for line, _code in run]
            yield from [_Block(run_lines, code=True)] if code else _text(run_lines)


def _tagged(lines: list[str]) -> Iterator[tuple[str, bool]]:
    """Each line with whether it belongs to a code block, its fences included."""
    fence = ""
    for line in lines:
        inside = bool(fence or _FENCE.match(line))
        fence = _fence_after(line, fence)
        yield line, inside


def _sections(tagged: Iterator[tuple[str, bool]]) -> Iterator[list[tuple[str, bool]]]:
    """The tagged lines cut before each heading of the first three levels outside code."""
    section: list[tuple[str, bool]] = []
    for line, code in tagged:
        if section and not code and _HEADING.match(line):
            yield section
            section = []
        section.append((line, code))
    if section:
        yield section


def _fence_after(line: str, fence: str) -> str:
    """The fence still open after ``line``: the one it opens, or ``fence`` until a line closes it."""
    marker = _FENCE.match(line)
    if not fence:
        return marker.group(1) if marker else ""
    closes = marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence)
    return "" if closes and not line.strip().lstrip(fence[0]) else fence


def _text(lines: list[str]) -> Iterator[_Block]:
    """``lines`` without the index table of the flows: a table whose rows start with a flow id."""
    table: list[str] = []
    kept: list[str] = []
    for line in [*lines, ""]:
        if _TABLE_ROW.match(line):
            table.append(line)
            continue
        if not any(re.fullmatch(_FLOW_ID, _first_cell(row)) for row in table):
            kept.extend(table)
        table = []
        kept.append(line)
    if kept[:-1]:
        yield _Block(kept[:-1])


def _first_cell(row: str) -> str:
    return row.strip().strip("|").split("|")[0].strip()


def _flow(flow_id: str, title: str, lines: list[str], words: Words) -> _Block:
    """A flow as the help publishes it: its title, steps and failure when done; nothing otherwise."""
    fields = _fields(lines, words)
    status = " ".join(line.strip() for line in fields.get(words.status, []))
    status = status.split(":", 1)[1].strip().casefold() if status else ""
    done = words.done.casefold()
    if not status.startswith(done) or status[len(done) : len(done) + 1].isalnum():
        return _Block([])
    published = [f"### {title}"]
    for key in (words.steps, words.failure):
        field = _trimmed(fields.get(key, []))
        if field:
            empty_key = field[0].rstrip().endswith(":")
            published += ([field[0], ""] if empty_key else [field[0]]) + field[1:] + [""]
    return _Block([*_trimmed(published), ""], flow_id=flow_id, title=title)


def _fields(lines: list[str], words: Words) -> dict[str, list[str]]:
    """The lines of each key of a flow, its own line first, until the next key."""
    key = re.compile(rf"^({'|'.join(re.escape(word) for word in words.keys)}):")
    fields: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        match = key.match(line)
        if match:
            current = fields.setdefault(match.group(1), [])
        if current is not None:
            current.append(line)
    return fields


def _trimmed(lines: list[str]) -> list[str]:
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


def _clean(lines: list[str], titles: dict[str, str], *, strict: bool) -> list[str]:
    """``lines`` with each published flow named by its «title» and without the references a reader cannot
    follow; ``strict``, for a published flow, also without the internal names between parentheses."""

    def named(match: re.Match[str]) -> str:
        return f"«{titles[match.group(0)]}»" if match.group(0) in titles else ""

    def unwanted(part: str) -> bool:
        unknown = any(reference not in titles for reference in _REFERENCE.findall(part))
        return unknown or bool(strict and _CODE_NAME.search(part))

    def clause(text: str) -> str:
        if strict and _PIXELS.search(text):
            return ""
        kept = ",".join(part for part in text.split(",") if not unwanted(part))
        return _REFERENCE.sub(named, kept).strip(_SEPARATORS)

    def parenthesis(match: re.Match[str]) -> str:
        clauses = match.group(1).split(";")
        kept = [cleaned for cleaned in map(clause, clauses) if cleaned]
        if kept == [written.strip(_SEPARATORS) for written in clauses]:
            return match.group(0)
        return f"{match.group(0)[: match.start(1) - match.start(0) - 1]}({'; '.join(kept)})" if kept else ""

    text = _REFERENCE.sub(named, _PARENTHESIS.sub(parenthesis, "\n".join(lines)))
    text = _DOUBLE_SPACE.sub(" ", _SPACE_BEFORE_MARK.sub("", text))
    return text.split("\n")
