"""Settings of the test run (pytest.ini): ``config.settings`` with the development defaults.

``config.settings`` keeps ``DEBUG`` off unless the environment turns it on, and pytest-django loads
the settings before any conftest runs, so the switch is set here, before they are read. The suite
then runs whether or not ``saas-next/.env`` exists; the production values are tested in a fresh
process (``config/tests/test_settings.py``). Vite's default port too, whatever the shell exports
(two SaaS at once, README): ``VITE_DEV_PORT`` is tested in a fresh process as well.
"""

import os

os.environ["DEBUG"] = "True"
os.environ.pop("VITE_DEV_PORT", None)

from config.settings import *  # noqa: E402, F403
