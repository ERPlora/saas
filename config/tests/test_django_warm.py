"""The warm Django of the panel's e2e (``tests/e2e/panel/django_warm.py``, saas#352), kept honest here because the CI
does not run the e2e: one process answers what each snippet prints, one line per snippet, and each snippet runs as
``python -c`` would run it after ``django.setup()`` (``djangoPrint`` of ``fixtures.ts``), so a spec that moves its
snippets there reads the same values as before.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "panel" / "django_warm.py"

# Each snippet gets the connection back to the pool, as the end of a ``python -c`` does: no test transaction around it.
pytestmark = pytest.mark.django_db(transaction=True)


def _load():
    spec = importlib.util.spec_from_file_location("django_warm", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    spec.loader.exec_module(module)
    return module


def served(*snippets: str) -> list[dict]:
    """What the warm Django answers to `snippets`, one request line each, read back line by line."""
    answers = io.StringIO()
    _load().serve((json.dumps({"code": snippet}) + "\n" for snippet in snippets), answers)
    return [json.loads(line) for line in answers.getvalue().splitlines()]


def test_it_says_it_is_ready_then_answers_each_snippet_with_what_it_printed():
    assert served('print("one")', 'print("two")\nprint("three")') == [
        {"ready": True},
        {"out": "one\n"},
        {"out": "two\nthree\n"},
    ]


def test_a_snippet_writes_to_the_run_database_and_the_next_one_reads_it():
    answers = served(
        'from django.contrib.auth import get_user_model\nget_user_model().objects.create_user(email="e2e-warm@example.com", password="x")',
        'from django.contrib.auth import get_user_model\nprint(get_user_model().objects.filter(email="e2e-warm@example.com").exists())',
    )
    assert answers[1:] == [{"out": ""}, {"out": "True\n"}]


def test_each_snippet_starts_from_no_names_of_the_one_before():
    answers = served("kept = 1", "print(kept)")
    assert answers[1] == {"out": ""}
    assert "NameError: name 'kept' is not defined" in answers[2]["error"]


def test_a_failing_snippet_answers_its_traceback_and_the_next_one_still_runs():
    answers = served('raise ValueError("no such account")', "import sys\nsys.exit(3)", 'print("after")')
    assert "ValueError: no such account" in answers[1]["error"]
    assert "SystemExit: 3" in answers[2]["error"]
    assert answers[3] == {"out": "after\n"}


def test_the_language_a_snippet_activates_does_not_reach_the_next_one():
    answers = served(
        'from django.utils import translation\ntranslation.activate("es")\nprint(translation.get_language())',
        "from django.utils import translation\nprint(translation.get_language())",
    )
    assert answers[1:] == [{"out": "es\n"}, {"out": "en\n"}]


def test_what_a_snippet_keeps_in_the_process_memory_cache_does_not_reach_the_next_one(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    answers = served(
        'from django.core.cache import cache\ncache.set("e2e-warm", "kept")\nprint(cache.get("e2e-warm"))',
        'from django.core.cache import cache\nprint(cache.get("e2e-warm"))',
    )
    assert answers[1:] == [{"out": "kept\n"}, {"out": "None\n"}]


def test_what_it_prints_outside_a_snippet_never_reaches_the_answers(monkeypatch, capsys):
    module = _load()
    # What an app prints as Django sets up (a warning, a banner) is no answer.
    monkeypatch.setattr(module, "setup_django", lambda: print("set up"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"code": 'print("asked")'}) + "\n"))
    with pytest.MonkeyPatch.context() as debug:
        from django.conf import settings

        debug.setattr(settings, "DEBUG", True)
        module.main([])
    out = capsys.readouterr().out
    assert [json.loads(line) for line in out.splitlines()] == [{"ready": True}, {"out": "asked\n"}]


def test_it_refuses_to_run_without_debug(monkeypatch, settings):
    module = _load()
    monkeypatch.setattr(module, "setup_django", lambda: None)
    settings.DEBUG = False
    with pytest.raises(SystemExit, match="only runs with DEBUG=True"):
        module.main([])
