"""Rule executor: apply validated rules to the Blue-visible event stream -> alerts.

Deterministic and LLM-free. Matching follows Sigma semantics: fields in a selection are ANDed,
a list of values for one field is ORed, string comparison is case-insensitive, a missing field
never matches. A rule only sees events of its logsource.category. Hidden ground-truth fields are
never read (the validator already forbids rules from naming them).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from src.rules.schema import VISIBLE_FIELDS, Rule
from src.rules.validator import validate_rule

_TOKEN_RE = re.compile(r"\s*(\(|\)|[A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class Alert:
    rule_id: str
    event_id: Any
    host_id: Any
    step: Any
    level: str
    confidence: float


def _norm(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _value_matches(event_value: Any, rule_value: Any, modifier: str | None) -> bool:
    if modifier is None:
        return _norm(event_value) == _norm(rule_value)
    if not isinstance(event_value, str) or not isinstance(rule_value, str):
        return False
    ev, rv = event_value.lower(), rule_value.lower()
    if modifier == "contains":
        return rv in ev
    if modifier == "startswith":
        return ev.startswith(rv)
    if modifier == "endswith":
        return ev.endswith(rv)
    return False


def _selection_matches(selection: dict[str, Any], event: dict[str, Any]) -> bool:
    for key, expected in selection.items():
        field, _, modifier = key.partition("|")
        if field not in VISIBLE_FIELDS or field not in event or event[field] is None:
            return False
        options = expected if isinstance(expected, list) else [expected]
        if not any(_value_matches(event[field], v, modifier or None) for v in options):
            return False
    return True


def _eval_condition(condition: str, results: dict[str, bool]) -> bool:
    tokens = [m.group(1) for m in _TOKEN_RE.finditer(condition)]
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def factor() -> bool:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok.lower() == "not":
            return not factor()
        if tok == "(":
            value = expr()
            pos += 1  # ')'
            return value
        return results[tok]

    def term() -> bool:
        nonlocal pos
        value = factor()
        while peek() is not None and peek().lower() == "and":
            pos += 1
            value = factor() and value
        return value

    def expr() -> bool:
        nonlocal pos
        value = term()
        while peek() is not None and peek().lower() == "or":
            pos += 1
            value = term() or value
        return value

    return expr()


def rule_matches(rule: Rule, event: dict[str, Any]) -> bool:
    if event.get("category") != rule.logsource["category"]:
        return False
    selections = {k: v for k, v in rule.detection.items() if k != "condition"}
    results = {name: _selection_matches(sel, event) for name, sel in selections.items()}
    return _eval_condition(str(rule.detection["condition"]), results)


class RuleExecutor:
    """Holds the active rule set. Invalid rules are rejected at load time, never executed."""

    def __init__(self, rules: Iterable[Rule] = ()):
        self.rules: list[Rule] = []
        self.rejected: list[tuple[str, list[str]]] = []
        for rule in rules:
            self.add(rule)

    def add(self, rule: Rule) -> bool:
        result = validate_rule(rule)
        if not result.valid:
            self.rejected.append((rule.rule_id, result.errors))
            return False
        self.rules.append(rule)
        return True

    def run(self, events: Iterable[dict[str, Any]]) -> list[Alert]:
        alerts: list[Alert] = []
        for event in events:
            for rule in self.rules:
                if rule_matches(rule, event):
                    alerts.append(Alert(
                        rule_id=rule.rule_id, event_id=event.get("event_id"),
                        host_id=event.get("host_id"), step=event.get("step"),
                        level=rule.level, confidence=float(rule.confidence),
                    ))
        return alerts
