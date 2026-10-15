"""The events of fiscal (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

fiscal reacts to no event of another app: ``events.py`` only names its own, and every one of them is recorded
by some command (none is dead weight in ``live.py``).
"""

import re
from pathlib import Path

from live.operations import NAME_RE

from fiscal import events

SERVICES_SOURCE = (Path(events.__file__).parent / "services.py").read_text()


def test_every_event_is_named_app_entity_fact_and_belongs_to_fiscal():
    assert events.ALL
    for name in events.ALL:
        assert NAME_RE.match(name) and name.startswith("fiscal."), name


def test_events_are_listed_once():
    assert len(events.ALL) == len(set(events.ALL))


def test_the_trail_names_each_decision():
    assert events.REPRESENTATION == [
        "fiscal.representation.submitted",
        "fiscal.representation.approved",
        "fiscal.representation.returned",
        "fiscal.representation.revoked",
    ]
    assert events.REPRESENTATION_CHANGED == "fiscal.representation.changed"


def test_every_event_is_recorded_by_a_command():
    """Each step by the command that takes it; ``changed`` by the system command that tells the owner and
    the admins of the business on their own channels (``fiscal.representation.notify``)."""
    constants = {value: key for key, value in vars(events).items() if isinstance(value, str) and value in events.ALL}
    recorded = set(re.findall(r"record_event\(ctx, events\.([A-Z_]+)", SERVICES_SOURCE))
    # Each step through ``_stepped``, which records it and what follows it (the business told, the snapshot).
    recorded |= set(re.findall(r"_stepped\(ctx, events\.([A-Z_]+)", SERVICES_SOURCE))

    assert {constants[name] for name in events.ALL} == recorded
