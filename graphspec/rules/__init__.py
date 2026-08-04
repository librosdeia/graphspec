"""Validation rule registry.

Each rule lives in its own module in this package and registers itself with the
``@rule`` decorator. Modules are auto-discovered, so adding a rule never touches
a shared file.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

from graphspec.diagnostics import Diagnostic
from graphspec.model import Graph

RuleFn = Callable[[Graph], list[Diagnostic]]

ALL_RULES: dict[str, RuleFn] = {}


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    """Register a rule function under its ID (e.g. ``E-EDGE-ENDS``)."""

    def register(fn: RuleFn) -> RuleFn:
        fn.rule_id = rule_id
        ALL_RULES[rule_id] = fn
        return fn

    return register


def _discover() -> None:
    for mod in pkgutil.iter_modules(__path__):
        if mod.name != "__init__":
            importlib.import_module(f"{__name__}.{mod.name}")


_discover()
