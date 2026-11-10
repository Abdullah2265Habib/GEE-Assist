"""gkonsol's commands, one module per group (``help`` lists them in this order)."""

from __future__ import annotations

from frontend.gkonsol.command import Registry
from frontend.gkonsol.commands import account, app, downloads, earth_engine, form, general, requests

MODULES = (general, account, earth_engine, form, requests, downloads, app)


def build_registry() -> Registry:
    """Every gkonsol command."""
    registry = Registry()
    for module in MODULES:
        module.register(registry)
    return registry
