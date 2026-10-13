"""Settings of the test run (pytest.ini): ``config.settings`` with the development defaults.

``config.settings`` keeps ``DEBUG`` off unless the environment turns it on, and pytest-django loads
the settings before any conftest runs, so the switch is set here, before they are read. The suite
then runs whether or not ``saas-next/.env`` exists; the production values are tested in a fresh
process (``config/tests/test_settings.py``).
"""

import os

os.environ["DEBUG"] = "True"

from config.settings import *  # noqa: E402, F403
