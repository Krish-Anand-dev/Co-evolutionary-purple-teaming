"""Legality check for CAGE-4 Red actions (T07; reused by the LLM Red validator in T20).

CybORG hands every Red agent an ``action_space`` dict each step:
  * ``action_space["action"]``: {ActionClass: bool}, which action classes are currently allowed
  * ``action_space[<param>]``: {value: bool}, which values of that parameter are currently allowed
An action is legal when its class is allowed and every parameter value it carries is allowed.
"""
from __future__ import annotations

import inspect
from typing import Any

IGNORED_PARAMS = ("self", "priority")


def action_params(action_cls: type) -> list[str]:
    """Names of the constructor parameters that are looked up in the action space."""
    return [p for p in inspect.getfullargspec(action_cls).args if p not in IGNORED_PARAMS]


def legal_commands(action_space: dict) -> dict[str, dict[str, list[Any]]]:
    """Every allowed action class with the allowed values of each of its parameters.

    A class whose parameter has no allowed value right now is left out.
    Returns {class_name: {"command": cls, <param>: [values...]}}.
    """
    commands: dict[str, dict[str, Any]] = {}
    for cls, allowed in action_space["action"].items():
        if not allowed:
            continue
        options: dict[str, Any] = {}
        for param in action_params(cls):
            values = [v for v, ok in action_space.get(param, {}).items() if ok]
            if not values:
                break
            options[param] = values
        else:
            options["command"] = cls
            commands[cls.__name__] = options
    return commands


def is_legal(action: Any, action_space: dict) -> tuple[bool, str]:
    """(True, "") if ``action`` may be played now, else (False, reason)."""
    cls = type(action)
    if not action_space["action"].get(cls, False):
        return False, f"action class {cls.__name__} not allowed"
    for param in action_params(cls):
        value = getattr(action, param, None)
        if not action_space.get(param, {}).get(value, False):
            return False, f"{cls.__name__}.{param}={value!r} not allowed"
    return True, ""
