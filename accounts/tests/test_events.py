"""The events of accounts (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

accounts reacts to no event of another app: ``events.py`` only names its own, and every one of them is
recorded by some command (none is dead weight in ``live.py``).
"""

import re
from pathlib import Path

from live.operations import NAME_RE

from accounts import events

SERVICES_SOURCE = (Path(events.__file__).parent / "services.py").read_text()


def test_every_event_is_named_app_entity_fact_and_belongs_to_accounts():
    assert events.ALL
    for name in events.ALL:
        assert NAME_RE.match(name) and name.startswith("accounts."), name


def test_events_are_listed_once():
    assert len(events.ALL) == len(set(events.ALL))


def test_every_event_is_recorded_by_a_command():
    constants = {value: key for key, value in vars(events).items() if isinstance(value, str) and value in events.ALL}
    recorded = set(re.findall(r"record_event\(ctx, events\.([A-Z_]+)", SERVICES_SOURCE))

    assert {constants[name] for name in events.ALL} == recorded
