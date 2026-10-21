"""whatsapp's events are named ``<app>.<entity>.<fact>`` and every one of them is listed."""

import re

from whatsapp import events

NAME = re.compile(r"^whatsapp\.[a-z_]+\.[a-z_]+$")


def test_every_event_is_named_after_its_app_entity_and_fact():
    names = [value for key, value in vars(events).items() if key.isupper() and key != "ALL"]

    assert names and all(NAME.match(name) for name in names)
    assert sorted(names) == sorted(events.ALL)
