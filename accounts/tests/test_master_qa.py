"""ACCOUNTS-F48: erplora.com's master QA is done only while every flow it rests on is.

The flow is a list in accounts/WORKBOOK.md («Para quien lo mantiene»): each section of the old QA and the flows that
cover it. These tests read that list and the WORKBOOK of each app of this repo, so a flow going back to `parcial` takes
the master QA with it instead of leaving a `hecho` nobody re-reads. The Hub's flows of the list (PRINTING, VERIFACTU and
INVOICE) live in its repo: their state is the registry's.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS_WORKBOOK = ROOT / "accounts" / "WORKBOOK.md"
APPS_OF_THIS_REPO = {"ACCOUNTS": "accounts", "APPS": "apps", "BILLING": "billing", "HUBS": "hubs", "PUBLIC": "public"}
#: A key of the list: `HUBS-F04`, a range `PUBLIC-F01–F37` or, after those, `F06` of the same app.
KEY = re.compile(r"(?:\b([A-Z_]+)-)?\bF(\d+)(?:–F(\d+))?")


def master_qa_keys() -> set[str]:
    text = ACCOUNTS_WORKBOOK.read_text(encoding="utf-8")
    start = text.index("La QA maestra (F48) es")
    listing = text[start + len("La QA maestra (F48) es") : text.index("No siguen, por la plataforma de ahora", start)]
    keys: set[str] = set()
    prefix = None
    for match in KEY.finditer(listing):
        prefix = match.group(1) or prefix
        first = int(match.group(2))
        for number in range(first, int(match.group(3) or first) + 1):
            keys.add(f"{prefix}-F{number:02d}")
    return keys


def state_of(key: str) -> str:
    """The first word of the flow's `Estado:` in the WORKBOOK of its app."""
    app = APPS_OF_THIS_REPO[key.split("-")[0]]
    text = (ROOT / app / "WORKBOOK.md").read_text(encoding="utf-8")
    found = re.search(rf"^### {key} .*\n(?:<!--.*-->\n)?Estado: (\w+)", text, re.MULTILINE)
    assert found, f"{key} is no flow of {app}/WORKBOOK.md"
    return found.group(1)


def test_the_list_names_the_flows_of_each_section_of_the_old_qa():
    keys = master_qa_keys()

    assert {"PUBLIC-F01", "PUBLIC-F37", "HUBS-F21", "BILLING-F06", "ACCOUNTS-F32", "APPS-F07"} <= keys
    assert {"PRINTING-F13", "VERIFACTU-F19", "INVOICE-F01"} <= keys
    assert len(keys) == 86


def test_every_flow_of_this_repo_it_rests_on_is_settled():
    states = {key: state_of(key) for key in master_qa_keys() if key.split("-")[0] in APPS_OF_THIS_REPO}

    assert {key: state for key, state in states.items() if state not in {"hecho", "descartado"}} == {}


def test_the_master_qa_is_done():
    assert state_of("ACCOUNTS-F48") == "hecho"


def test_the_app_is_complete_with_no_flow_left_partial():
    text = ACCOUNTS_WORKBOOK.read_text(encoding="utf-8")

    assert re.search(r"^Estado de la app: completa \(\d{4}-\d{2}-\d{2}\)$", text, re.MULTILINE)
    assert re.findall(r"^### (ACCOUNTS-F\d+) .*\n(?:<!--.*-->\n)?Estado: parcial", text, re.MULTILINE) == []
