"""``config.tests.asgi_bodies.files_written``: the watch the in-memory body tests trust.

It must see every file the process opens to write (a library's temporary file included) and nothing else: a module
imported for the first time inside a watch writes its ``.pyc`` (``os.open`` on ``__pycache__`` and then
``FileIO(fd, "wb")``), and the watch counted that descriptor as a written file (an intermittent failure of
``assistant/tests/test_body_in_memory.py`` on a cold cache).
"""

import importlib
import os
import sys
import tempfile
import uuid

from config.tests.asgi_bodies import files_written


def test_a_module_imported_cold_inside_the_watch_is_not_a_written_file(tmp_path, monkeypatch):
    name = f"cold_{uuid.uuid4().hex}"
    (tmp_path / f"{name}.py").write_text("VALUE = 1\n")
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    try:
        with files_written() as written:
            assert importlib.import_module(name).VALUE == 1
    finally:
        sys.modules.pop(name, None)

    assert list((tmp_path / "__pycache__").iterdir()), "the import did not write its bytecode: nothing was tested"
    assert written == []


def test_a_file_opened_to_write_is_seen_whichever_way_it_is_opened(tmp_path):
    with files_written() as written:
        with open(tmp_path / "plain", "wb") as plain:
            plain.write(b"x")
        os.close(os.open(tmp_path / "low", os.O_WRONLY | os.O_CREAT))
        with tempfile.TemporaryFile(dir=tmp_path) as spool:
            spool.write(b"x")

    assert str(tmp_path / "plain") in written
    assert str(tmp_path / "low") in written
    assert len(written) >= 3


def test_reading_a_file_is_not_writing_it(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"x")

    with files_written() as written:
        assert source.read_bytes() == b"x"

    assert written == []
