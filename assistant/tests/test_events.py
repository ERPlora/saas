"""The assistant's events (``assistant.events``): each named ``assistant.<entity>.<fact>``, all of them in ``ALL``."""

from live.outbox import NAME_RE

from assistant import events


def test_every_event_is_named_assistant_entity_fact():
    names = [value for name, value in vars(events).items() if name.isupper() and name != "ALL"]

    assert names
    assert sorted(names) == sorted(events.ALL)
    for name in names:
        assert NAME_RE.match(name) and name.startswith("assistant."), name
