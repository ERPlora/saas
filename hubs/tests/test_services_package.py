"""The writes of hubs live one module per entity or use case; the package itself only gathers them.

A name re-exported from ``hubs/services/__init__.py`` would give every write two import paths again, and a
patch through the package would no longer reach the module that calls the name.
"""

from pathlib import Path

from django.conf import settings

from hubs.tests.test_queries_package import statements_beyond_gathering

PACKAGE = Path(settings.BASE_DIR) / "hubs" / "services"


def test_the_package_only_gathers_its_modules():
    assert statements_beyond_gathering((PACKAGE / "__init__.py").read_text(), "hubs.services") == []


def test_the_scan_catches_a_re_exported_write_and_code_of_its_own():
    module = next(path.stem for path in sorted(PACKAGE.glob("*.py")) if path.stem != "__init__")
    source = (
        '"""Docstring."""\n'
        f"from hubs.services import {module}\n"
        f"from hubs.services.{module} import something\n"
        f"from hubs.services import {module} as renamed\n"
        "from hubs.queries import access_control\n"
        "LIMIT = 3\n"
    )

    assert statements_beyond_gathering(source, "hubs.services") == [
        f"line 3: from hubs.services.{module} import something",
        f"line 4: from hubs.services import {module} as renamed",
        "line 5: from hubs.queries import access_control",
        "line 6: LIMIT = 3",
    ]
