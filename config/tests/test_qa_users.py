"""The QA users of the e2e seeds come from the environment, their constants as defaults.

The root ``.env`` of erplora-next lists them (``QA_*``, README «Usuarios QA»), with the same values the seeds
fall back to, so both agree by construction; exported (``set -a; . ../.env; set +a``), they are the ones the
seeds create and the specs sign in with (``tests/e2e/panel/fixtures.ts``). ``demo_seed``'s are
``hubs/tests/test_demo_seed.py``'s.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "panel"


def _load(name: str):
    """The seed script as a fresh module: it reads the environment when it is imported."""
    spec = importlib.util.spec_from_file_location(f"qa_{name}", PANEL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "seed, role, email, password",
    [
        ("billing_seed", "BILLING", "e2e-billing@example.com", "e2e-panel"),
        ("store_seed", "STORE", "e2e-store@example.com", "e2e-panel"),
    ],
)
def test_the_account_of_a_seed_is_the_environments_or_its_default(monkeypatch, seed, role, email, password):
    monkeypatch.delenv(f"QA_{role}_EMAIL", raising=False)
    monkeypatch.delenv(f"QA_{role}_PASSWORD", raising=False)
    assert (_load(seed).EMAIL, _load(seed).PASSWORD) == (email, password)

    monkeypatch.setenv(f"QA_{role}_EMAIL", f"qa-{role.lower()}@example.com")
    monkeypatch.setenv(f"QA_{role}_PASSWORD", "qa-pass")
    module = _load(seed)

    assert (module.EMAIL, module.PASSWORD) == (f"qa-{role.lower()}@example.com", "qa-pass")


def test_the_panel_accounts_share_the_environments_password_or_its_default(monkeypatch):
    monkeypatch.delenv("QA_PANEL_PASSWORD", raising=False)
    assert _load("panel_seed").PASSWORD == "e2e-panel"

    monkeypatch.setenv("QA_PANEL_PASSWORD", "qa-panel-pass")

    assert _load("panel_seed").PASSWORD == "qa-panel-pass"
