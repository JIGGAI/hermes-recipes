"""Simulate Hermes's plugin discovery flow against the entry point.

Mirrors the behavior of ``hermes_cli/plugins.py:_scan_entry_points`` +
``_load_entrypoint_module`` so we catch regressions in the registration
contract without needing a real Hermes install on the test runner.
"""

import importlib.metadata as md
from unittest.mock import MagicMock

import pytest


HERMES_PLUGIN_GROUP = "hermes_agent.plugins"
EXPECTED_ENTRY_POINT_NAME = "hermes_recipes"


def _our_entry_points() -> list[md.EntryPoint]:
    eps = md.entry_points()
    if hasattr(eps, "select"):
        return list(eps.select(group=HERMES_PLUGIN_GROUP))
    return [ep for ep in eps if getattr(ep, "group", None) == HERMES_PLUGIN_GROUP]


def test_entry_point_is_discoverable():
    eps = _our_entry_points()
    names = [ep.name for ep in eps]
    assert EXPECTED_ENTRY_POINT_NAME in names, (
        f"Expected '{EXPECTED_ENTRY_POINT_NAME}' in {HERMES_PLUGIN_GROUP}; "
        f"got {names}. Did pyproject.toml lose its [project.entry-points] block?"
    )


def test_entry_point_loads_to_module_with_register():
    eps = _our_entry_points()
    ep = next(ep for ep in eps if ep.name == EXPECTED_ENTRY_POINT_NAME)
    module = ep.load()
    register = getattr(module, "register", None)
    assert callable(register), "Entry point target must expose a callable `register`."


def test_hermes_style_load_calls_register_with_plugin_context():
    """End-to-end: load the entry point and invoke it with a Hermes-like context.

    This is the same shape Hermes's PluginManager runs at startup:
      manifest = PluginManifest(name=ep.name, source='entrypoint', path=ep.value)
      module = ep.load()
      register(ctx)
    """
    eps = _our_entry_points()
    ep = next(ep for ep in eps if ep.name == EXPECTED_ENTRY_POINT_NAME)
    module = ep.load()

    ctx = MagicMock()
    module.register(ctx)
    ctx.register_cli_command.assert_called_once()
    kwargs = ctx.register_cli_command.call_args.kwargs
    assert kwargs["name"] == "recipes"
    assert callable(kwargs["setup_fn"])
    assert callable(kwargs["handler_fn"])
