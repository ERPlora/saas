"""A WORKBOOK holds only what serves today: the flows, rules and contracts that exist.

A dropped flow is deleted, not marked; a struck-through note, the comment saying where a section came from and a
comparison with the old product are history, and history lives in git, the pull requests and the plans. The scan
reads every WORKBOOK of this repository, the Spanish one and its English translation.
"""

import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKIPPED_FOLDERS = {"node_modules", "packages"}
WORKBOOK_NAME = re.compile(r"WORKBOOK(?:\.[a-z]{2})?\.md")
APPS_WITH_A_WORKBOOK = {"accounts", "apps", "assistant", "billing", "fiscal_gateway", "hubs", "public", "whatsapp"}

DROPPED = r"(?:descartad[oa]s?|discarded)\b"
RULES = (
    ("dropped flow", re.compile(rf"^\|\s*[A-Z][A-Z_]*-F\d+\s*\|.*\|\s*{DROPPED}[^|]*\|\s*$", re.IGNORECASE)),
    ("dropped flow", re.compile(rf"^(?:Estado|Status|State):\s*{DROPPED}", re.IGNORECASE)),
    ("struck-through text", re.compile(r"~~")),
    ("origin comment", re.compile(r"<!--\s*origen:", re.IGNORECASE)),
    (
        "old product",
        re.compile(r"\b(?:hub|saas|producto)s?\s+viejos?\b|\bold[\s-](?:hub|saas|product)s?\b", re.IGNORECASE),
    ),
)


def violations(text: str) -> list[tuple[int, str, str]]:
    """Each line of ``text`` that keeps history, as (line number, rule, line)."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        found += [(number, rule, line.strip()) for rule, pattern in RULES if pattern.search(line)]
    return found


def workbooks(root: Path) -> list[Path]:
    """Every WORKBOOK under ``root``, leaving out dependencies, submodules and hidden folders."""
    found = []
    for folder, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in SKIPPED_FOLDERS and not name.startswith(".")]
        found += [Path(folder) / name for name in files if WORKBOOK_NAME.fullmatch(name)]
    return sorted(found)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("| PUBLIC-F36 | Pedir una demo desde otra aplicación | descartado |", "dropped flow"),
        ("| FISCAL-F07 | Watch the powers of attorney | discarded |", "dropped flow"),
        ("Estado: descartado — nadie lo usaba.", "dropped flow"),
        ("Status: discarded — nobody used it.", "dropped flow"),
        ("~~El enlace caducaba en un día~~ — cerrada (antes).", "struck-through text"),
        ("<!-- origen: copiado tal cual -->", "origin comment"),
        ("Igual que en el hub viejo, la lista se ordena por fecha.", "old product"),
        ("El SaaS viejo pedía la clave dos veces.", "old product"),
        ("Lo que el Producto Viejo guardaba.", "old product"),
        ("Like the old SaaS, it asks twice.", "old product"),
        ("ERPlora's old product kept the keys.", "old product"),
    ],
)
def test_each_kind_of_history_is_caught(text, rule):
    assert violations(f"## Flujos\n\n{text}\n") == [(3, rule, text)]


def test_what_describes_the_product_of_today_is_left_alone():
    text = """<!-- generated from WORKBOOK.md sha256:0000 -->
| PUBLIC-F12 | Llegar a una dirección retirada | hecho |
| HUBS-F03 | Descartado: vaciar la papelera | hecho |
Estado: hecho
Estado de la app: completa
El aviso dice «Descartado.» y la fila desaparece.
Un código retirado lleva para siempre al vigente.
One of a number nobody has connected is discarded.
El hub vuelve a abrir el ticket viejo del cliente.
"""

    assert violations(text) == []


def test_the_workbooks_of_this_repository_keep_no_history():
    found = workbooks(REPO)
    assert {path.parent.name for path in found} >= APPS_WITH_A_WORKBOOK, "the scan missed a WORKBOOK"

    history = [
        f"{path.relative_to(REPO)}:{number}: {rule}: {line}"
        for path in found
        for number, rule, line in violations(path.read_text(encoding="utf-8"))
    ]
    assert history == [], "\n".join(history)


def test_the_walk_skips_dependencies_and_submodules(tmp_path):
    for place in ("hubs", "node_modules/x", "packages/live", ".venv/lib"):
        (tmp_path / place).mkdir(parents=True)
        (tmp_path / place / "WORKBOOK.md").write_text("~~x~~\n", encoding="utf-8")
    (tmp_path / "hubs" / "WORKBOOK.en.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "hubs" / "README.md").write_text("ok\n", encoding="utf-8")

    assert workbooks(tmp_path) == [tmp_path / "hubs" / "WORKBOOK.en.md", tmp_path / "hubs" / "WORKBOOK.md"]
