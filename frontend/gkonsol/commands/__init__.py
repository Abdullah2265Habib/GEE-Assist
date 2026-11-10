"""gkonsol's commands, one module per group (``help`` lists them in this order)."""

from __future__ import annotations

from frontend.gkonsol.command import Registry


def build_registry() -> Registry:
    """Every gkonsol command."""
    registry = Registry()
    return registry
