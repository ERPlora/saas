"""The messages of a template, read as ``makemessages`` reads them."""

import ast
import re
from pathlib import Path

from django.utils.translation.template import templatize

_LITERAL = r"u?'(?:[^'\\]|\\.)*'|u?\"(?:[^\"\\]|\\.)*\""
#: The calls ``templatize`` writes for {% trans %}, {% blocktrans %} and a ``_("…")`` argument of a tag, such as the
#: label of a {% button %} (what makemessages reads).
_CALL = re.compile(
    rf"\b(gettext|pgettext|ngettext|npgettext|_)\(((?:{_LITERAL})(?:, (?:{_LITERAL}))*)"
)


def template_messages(path: Path) -> list[str]:
    """The catalog keys of every message of a template, as ``makemessages`` would extract them."""
    source = templatize(path.read_text(encoding="utf-8"), origin=str(path))
    keys = []
    for function, arguments in _CALL.findall(source):
        literals = [ast.literal_eval(raw) for raw in re.findall(_LITERAL, arguments)]
        if function in ("gettext", "_"):
            keys.append(literals[0])
        elif function == "pgettext":
            keys.append(f"{literals[0]}\x04{literals[1]}")
        elif function == "ngettext":
            keys.append((literals[0], 0))
        else:
            keys.append((f"{literals[0]}\x04{literals[1]}", 0))
    return keys
