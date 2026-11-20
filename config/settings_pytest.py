"""Settings of the test run (pytest.ini): ``config.settings`` with the development defaults.

``config.settings`` keeps ``DEBUG`` off unless the environment turns it on, and pytest-django loads
the settings before any conftest runs, so the switch is set here, before they are read. The suite
then runs whether or not the repo's ``.env`` exists; the production values are tested in a fresh
process (``config/tests/test_settings.py``). Vite's default port too, whatever the shell exports or
``.env`` says (two SaaS at once, README; the environment wins over ``.env`` in python-decouple):
``VITE_DEV_PORT`` is tested in a fresh process as well. reCAPTCHA is off (``RECAPTCHA_ENABLED``), whatever ``.env``
holds: the test run never asks Google. The assistant's web search is off too (``BRAVE_SEARCH_API_KEY``), as in the CI,
and so is every AI provider's key.
"""

import os

os.environ["DEBUG"] = "True"
os.environ["VITE_DEV_PORT"] = "5174"
# reCAPTCHA off, whatever `.env` holds: no test asks Google. A test that checks a form switches it on with the
# `recaptcha` fixture (conftest.py), which plays Google.
os.environ["RECAPTCHA_ENABLED"] = "False"
# The web search off, whatever `.env` holds: no test asks Brave. A test that needs it on sets
# `settings.BRAVE_SEARCH_API_KEY`.
os.environ["BRAVE_SEARCH_API_KEY"] = ""
# No AI provider's key, whatever the shell or `.env` holds: no test reaches a real provider with a real key. A test
# that needs one sets it on `settings` (assistant/tests/conftest.py, `openai_key`).
for _name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
    os.environ[_name] = ""

from config.settings import *  # noqa: E402, F403
