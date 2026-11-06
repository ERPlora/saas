"""A warm Django for the panel's e2e (saas#352): ONE process per Playwright worker runs what a test asks the SaaS's
Django, so no test pays a Django boot nor blocks the process that drives it (``djangoPrintWarm`` of ``fixtures.ts``;
the recipe of saas#328's ``billing_stripe_played.py serve``).

From saas-next/, against the database of the run (development only, refused without ``DEBUG``):
``uv run python tests/e2e/panel/django_warm.py``. Django starts once, says ``{"ready": true}``, and then answers each
JSON line it reads on its stdin with one JSON line, in order, until its stdin ends:

- ``{"code": <Python>}`` → ``{"out": <what it printed>}``: the snippet runs as ``python -c`` runs it after
  ``django.setup()`` (``djangoPrint``): from no names of the one before, its connection back to the pool and the
  language, the time zone and this process's memory cache it touched gone when it ends;
- a snippet that fails (``SystemExit`` too) → ``{"error": <its traceback>}``, and the next one is answered as usual.

Its stdout carries only those lines; whatever is printed outside a snippet goes to its stderr.
"""

import io
import json
import os
import sys
import traceback
from collections.abc import Iterable
from contextlib import redirect_stdout
from pathlib import Path
from typing import TextIO

SAAS_DIR = Path(__file__).resolve().parents[3]


def setup_django() -> None:
    sys.path.insert(0, str(SAAS_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _say(answers: TextIO, answer: dict) -> None:
    answers.write(json.dumps(answer) + "\n")
    answers.flush()


def _run(code: str) -> dict:
    """What `code` printed, as a fresh ``python -c`` leaves things once it ends."""
    from django.core.cache import caches
    from django.core.cache.backends.locmem import LocMemCache
    from django.db import close_old_connections
    from django.utils import timezone, translation

    printed = io.StringIO()
    try:
        with redirect_stdout(printed):
            exec(compile(code, "<e2e snippet>", "exec"), {"__name__": "__main__"})
    except (Exception, SystemExit):
        # The spec waits for this line: it rejects that call with the traceback, and the next call still runs.
        return {"error": traceback.format_exc()}
    finally:
        translation.deactivate()
        timezone.deactivate()
        close_old_connections()
        # This process's memory dies with a `python -c`; a shared Valkey (VALKEY_URL) is the run's, never cleared here.
        for cache in caches.all(initialized_only=True):
            if isinstance(cache, LocMemCache):
                cache.clear()
    return {"out": printed.getvalue()}


def serve(requests: Iterable[str], answers: TextIO) -> None:
    """``{"ready": true}``, then one answer line per request line of ``requests``, in order, until they end."""
    _say(answers, {"ready": True})
    for line in requests:
        _say(answers, _run(json.loads(line)["code"]))


def main(argv: list[str]) -> None:
    answers = sys.stdout
    with redirect_stdout(sys.stderr):
        setup_django()
        from django.conf import settings

        if not settings.DEBUG:
            sys.exit("django_warm.py only runs with DEBUG=True")
        if argv:
            sys.exit("usage: django_warm.py (one JSON line per snippet on its stdin)")
        serve(sys.stdin, answers)


if __name__ == "__main__":
    main(sys.argv[1:])
