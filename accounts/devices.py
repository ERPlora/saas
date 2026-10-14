"""What a user agent says about where a session runs (Account → Security → Active sessions).

Ported from the old hub's ``default_device_name`` (``crates/server/src/devices.rs``): proper nouns for the
browser and codes for the device, nothing to translate in the database (the panel names each device in the
reader's language). The ERPlora app says so in its user agent (``ERPloraApp/<version>``, as the shell's
``surface.ts`` reads it); then the browser underneath is not what the person would name. An agent that says
nothing yields empty answers: inventing «Device 1» would be a lie.
"""

import re
from dataclasses import dataclass

_APP = re.compile(r"\bERPloraApp/(\S+)")
#: Most specific first: Edge and Opera announce Chrome, and Chrome announces Safari.
_BROWSERS = (
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/(\d+)")),
    ("Opera", re.compile(r"\bOPR/(\d+)")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/(\d+)")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/(\d+)")),
    ("Safari", re.compile(r"\bVersion/(\d+)[.\d]*(?: Mobile/\S+)? Safari/")),
)
#: ``iPad``/``iPhone`` before ``Mac OS X``, which they also carry; ``Android`` before ``Linux``, same.
_PLATFORMS = (
    ("ipad", "iPad"),
    ("iphone", "iPhone"),
    ("android", "Android"),
    ("windows", "Windows"),
    ("chromeos", "CrOS"),
    ("mac", "Macintosh"),
    ("mac", "Mac OS X"),
    ("linux", "Linux"),
)


@dataclass(frozen=True)
class Device:
    #: ``iphone``, ``ipad``, ``android``, ``windows``, ``chromeos``, ``mac``, ``linux`` or ``""``.
    platform: str
    #: ``Chrome``, ``Safari``, ``Firefox``, ``Edge``, ``Opera`` or ``""`` (also inside the app).
    browser: str
    #: The browser's major version, or ``""``.
    browser_version: str
    #: The ERPlora app's version when the session runs in it.
    app_version: str | None


def describe(user_agent: str) -> Device:
    platform = next((code for code, token in _PLATFORMS if token in user_agent), "")
    app = _APP.search(user_agent)
    if app is not None:
        return Device(platform, "", "", app.group(1))
    for name, pattern in _BROWSERS:
        match = pattern.search(user_agent)
        if match is not None:
            return Device(platform, name, match.group(1), None)
    return Device(platform, "", "", None)
