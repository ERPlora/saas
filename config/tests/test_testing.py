"""The check of ``conftest.py`` on the database connections (config/testing.py).

A test that patches ``ensure_connection`` on the connection itself, rather than on its class, gets
back at ``monkeypatch``'s undo the real method it read while it had the database, now on the
connection: it hides pytest-django's block from every later test of the process without the
database, which then queries instead of failing (saas#324). Once its fixtures are torn down, the
test that leaves one fails, saying which connection, and the method is removed so that the next
test starts clean.
"""

import pytest
from django.db import DEFAULT_DB_ALIAS, connections

from config import testing
from config.testing import database_block_left_as_found, discard_hidden_blocks


def left_on_the_connection(name: str):
    """The connection of this thread keeps its method ``name`` on itself, as ``monkeypatch``'s
    undo leaves it."""
    wrapper = connections[DEFAULT_DB_ALIAS]
    setattr(wrapper, name, getattr(wrapper, name))
    return wrapper


def test_a_connection_left_with_its_own_ensure_connection_is_found_and_removed():
    wrapper = left_on_the_connection("ensure_connection")
    assert discard_hidden_blocks() == [DEFAULT_DB_ALIAS]
    # Removed: the method is the class's again, blocked or not as pytest-django says.
    assert "ensure_connection" not in vars(wrapper)
    assert discard_hidden_blocks() == []


def test_what_django_itself_keeps_on_a_connection_hides_no_block():
    # SimpleTestCase puts cursor, connect… back on the connections a test does not use, on the
    # connection itself: they still go through ensure_connection. A cached_property and a flag
    # live there too.
    wrapper = left_on_the_connection("cursor")
    assert wrapper.timezone_name
    wrapper.force_debug_cursor = True
    try:
        assert discard_hidden_blocks() == []
    finally:
        del wrapper.cursor
        wrapper.force_debug_cursor = False


def test_the_check_fails_the_test_that_leaves_one_and_says_which_connection():
    check = database_block_left_as_found(None, None)
    next(check)
    wrapper = left_on_the_connection("ensure_connection")
    said = rf"own ensure_connection on the database connection {DEFAULT_DB_ALIAS}:"
    with pytest.raises(pytest.fail.Exception, match=said):
        check.send(None)
    assert "ensure_connection" not in vars(wrapper)


def test_the_check_lets_a_test_that_leaves_none_pass():
    check = database_block_left_as_found(None, None)
    next(check)
    with pytest.raises(StopIteration):
        check.send(None)


def test_every_test_is_checked_once_its_fixtures_are_torn_down(request):
    # A wrapper around pytest's own teardown, the one that undoes monkeypatch: it checks once that
    # one is done. As a plain hook, pluggy would only build the generator and no test would ever be
    # checked.
    teardowns = request.config.hook.pytest_runtest_teardown.get_hookimpls()
    [check] = [hook for hook in teardowns if hook.function is testing.database_block_left_as_found]
    assert check.wrapper
