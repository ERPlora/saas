"""The signals accounts sends for the apps that depend on it (``accounts ← hubs``: accounts never imports
hubs). Each is sent inside the command's transaction, so a receiver that queues work commits or rolls back
with it."""

from django.dispatch import Signal

from accounts import signals


def test_the_signals_other_apps_listen_to():
    assert isinstance(signals.sessions_ended, Signal)
    assert isinstance(signals.account_deleting, Signal)


def test_they_are_two_different_signals():
    assert signals.sessions_ended is not signals.account_deleting
