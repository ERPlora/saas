"""The shape of ``config.settings``: a package of modules, one per concern, that Django reads as one."""

import ast
import importlib
import pkgutil
from pathlib import Path

import config.settings as project_settings

SETTINGS = Path(project_settings.__file__).resolve().parent
MISSING = object()


def is_setting(name: str) -> bool:
    """What ``diffsettings`` shows: upper-case and public (``_ENV_FILE`` is the settings' own detail)."""
    return name.isupper() and not name.startswith("_")


def modules() -> list[str]:
    return sorted(info.name for info in pkgutil.iter_modules([str(SETTINGS)]))


def defined_settings(tree: ast.Module) -> set[str]:
    """The settings a module assigns at its top level, inside its top-level ``if`` and ``try`` blocks too."""
    names = set()
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.If, ast.Try, ast.ExceptHandler)):
            pending.extend(ast.iter_child_nodes(node))
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        names.update(target.id for target in targets if isinstance(target, ast.Name) and is_setting(target.id))
    return names


def test_the_settings_are_a_package_with_no_module_beside_it():
    """Python imports the package and ignores a ``config/settings.py`` next to it: a setting written there is lost."""
    assert SETTINGS == Path(__file__).resolve().parents[1] / "settings"
    assert (SETTINGS / "__init__.py").is_file()
    assert not (SETTINGS.parent / "settings.py").exists()
    assert len(modules()) > 1


def test_every_setting_of_every_module_reaches_django():
    """A module the package forgets to import, or one whose names stay private, is a setting Django never reads."""
    missing = {
        f"{name}.{setting}"
        for name in modules()
        for setting, value in vars(importlib.import_module(f"config.settings.{name}")).items()
        if is_setting(setting) and getattr(project_settings, setting, MISSING) is not value
    }

    assert missing == set()


def test_each_setting_is_defined_in_one_module():
    """Two modules that define the same setting override each other silently, by the order of their imports."""
    owners: dict[str, list[str]] = {}
    for name in modules():
        tree = ast.parse((SETTINGS / f"{name}.py").read_text())
        for setting in defined_settings(tree):
            owners.setdefault(setting, []).append(name)

    assert {setting: names for setting, names in owners.items() if len(names) > 1} == {}
    assert {"DEBUG", "INSTALLED_APPS", "DATABASES", "SECURE_CSP", "STRIPE_SECRET_KEY"} <= owners.keys()
