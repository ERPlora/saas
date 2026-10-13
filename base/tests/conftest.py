"""Fixtures of base's tests."""

import psycopg
import pytest
from django.db import connections


@pytest.fixture
def other_session(django_db_setup):
    """A second database session, as a second task (another saas-cron or saas-migrate) would have."""
    params = connections["default"].settings_dict
    session = psycopg.connect(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
        autocommit=True,
    )
    yield session
    session.close()
