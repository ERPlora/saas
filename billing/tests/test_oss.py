"""The OSS warning share lives outside ``billing.services`` (``billing/oss.py``), so the mail that tells it
(``billing.emails``) never imports the writes that send it: each would need the other. An import written inside a
function counts too, because it only puts the cycle off until the call."""

import ast
from pathlib import Path

from django.conf import settings

BILLING = Path(settings.BASE_DIR) / "billing"
SERVICES = "billing.services"


def _imported_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """The dotted names an import brings in; a relative one is read from ``billing/``, where the mail lives."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    package = ".".join(part for part in ("billing" if node.level else "", node.module or "") if part)
    return [package, *(f"{package}.{alias.name}" for alias in node.names)]


def services_imports(source: str) -> list[str]:
    return [
        f"line {node.lineno}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        and any(name == SERVICES or name.startswith(f"{SERVICES}.") for name in _imported_names(node))
    ]


def test_the_scan_catches_its_positive():
    in_a_function = "def send():\n    from billing.services.oss_notices import OSS_WARNING_PERCENT\n"

    assert services_imports(in_a_function) == ["line 2"]
    assert services_imports("from billing import services")
    assert services_imports("import billing.services.oss_notices")
    assert services_imports("from .services import oss_notices")
    assert services_imports("from . import services")
    assert services_imports("from billing import emails, money\nfrom billing.money import from_cents") == []


def test_the_mail_never_imports_the_writes_that_send_it():
    assert services_imports((BILLING / "emails.py").read_text(encoding="utf-8")) == []
