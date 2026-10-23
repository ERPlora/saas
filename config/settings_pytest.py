"""Settings of the test run (pytest.ini): ``config.settings`` with the development defaults.

``config.settings`` keeps ``DEBUG`` off unless the environment turns it on, and pytest-django loads
the settings before any conftest runs, so the switch is set here, before they are read. The suite
then runs whether or not ``saas-next/.env`` exists; the production values are tested in a fresh
process (``config/tests/test_settings.py``). Vite's default port too, whatever the shell exports or
``.env`` says (two SaaS at once, README; the environment wins over ``.env`` in python-decouple):
``VITE_DEV_PORT`` is tested in a fresh process as well. reCAPTCHA is off (``RECAPTCHA_ENABLED``), whatever ``.env``
holds: the test run never asks Google.
"""

import os

os.environ["DEBUG"] = "True"
os.environ["VITE_DEV_PORT"] = "5174"
# reCAPTCHA off, whatever `.env` holds: no test asks Google. A test that checks a form switches it on with the
# `recaptcha` fixture (conftest.py), which plays Google.
os.environ["RECAPTCHA_ENABLED"] = "False"

from config.settings import *  # noqa: E402, F403
