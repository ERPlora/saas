"""What the test harness of ``conftest.py`` checks on the database connections once a test ends:
connections left with their own ``ensure_connection`` (``database_block_left_as_found``).

Same check as the Hub's ``config/testing.py``.
"""

import pytest
from django.db import connections

#: The method pytest-django blocks for a test without the database, on the connections' class
#: (``BaseDatabaseWrapper.ensure_connection``), as Django's ``SimpleTestCase`` does.
BLOCKED = "ensure_connection"


def discard_hidden_blocks() -> list[str]:
    """The aliases of this thread's connections that keep their own ``ensure_connection``, over
    their class's: what ``monkeypatch.setattr(connection, "ensure_connection", …)`` leaves when it
    is undone, the real method it read while the test had the database. Each one is removed, so the
    connection answers with its class's again, blocked or not as pytest-django says.

    Only that method: Django's ``SimpleTestCase`` puts back ``connect``, ``cursor``… on the
    connections a test does not use, on the connection itself, and those still go through
    ``ensure_connection``."""
    found: list[str] = []
    for wrapper in connections.all(initialized_only=True):
        if BLOCKED in vars(wrapper):
            found.append(wrapper.alias)
            delattr(wrapper, BLOCKED)
    return sorted(found)


@pytest.hookimpl(wrapper=True)
def database_block_left_as_found(item, nextitem):
    """The ``pytest_runtest_teardown`` of ``conftest.py``: once every fixture of the test is torn
    down, ``monkeypatch`` included, fails the test that left a connection with its own
    ``ensure_connection`` (saas#324).

    A test that patches it on the connection itself gets back, at the undo, the real method it read
    while it had the database, now on the connection: it hides pytest-django's block, and a later
    test of the same process without the database queries instead of failing (it passes on one
    machine and fails in another worker of ``-n 4``). The method is removed, so the next test
    starts clean."""
    try:
        return (yield)
    finally:
        if left := discard_hidden_blocks():
            pytest.fail(
                f"left its own {BLOCKED} on the database connection {', '.join(left)}: patching "
                "the connection leaves the real method on it at the undo, which hides "
                "pytest-django's block from every later test without the database in the process. "
                "Patch its class instead, type(connections[alias]).",
                pytrace=False,
            )
