"""Throw-away operations for ``test_api_auth.py``: registered by its fixture and removed after each test.

They live in ``queries.py`` and ``services.py`` because ``@operation`` only accepts a query from a queries
module and a command from a services module; they are plain functions until the fixture declares them."""
