"""Rule validator: schema check, vocabulary check, condition grammar, RuleValidity.

A rule is valid only if every check passes. Errors are collected (not raised) so the Blue agent
can be shown why a rule failed and so RuleValidity can be computed over a batch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.rules.schema import (
    EVENT_CATEGORIES, HIDDEN_FIELDS, LEVELS, MAX_RATIONALE_CHARS, MODIFIERS, VISIBLE_FIELDS, Rule,
)

_REQUIRED = ("rule_id", "round", "agent_id", "title", "level", "logsource", "detection", "confidence")
_AGENT_RE = re.compile(r"^blue_\d+$")
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOKEN_RE = re.compile(r"\s*(\(|\)|[A-Za-z_][A-Za-z0-9_]*)")
_OPERATORS = {"and", "or", "not"}
_SCALARS = (str, int, float, bool)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def _split_field(key: str) -> tuple[str, str | None]:
    base, _, modifier = key.partition("|")
    return base, (modifier or None)


def _check_selection(name: str, sel: Any, errors: list[str]) -> None:
    if not isinstance(sel, dict) or not sel:
        errors.append(f"selection '{name}' must be a non-empty mapping field -> value(s)")
        return
    for key, value in sel.items():
        base, modifier = _split_field(str(key))
        if base in HIDDEN_FIELDS:
            errors.append(f"selection '{name}' uses hidden ground-truth field '{base}'")
        elif base not in VISIBLE_FIELDS:
            errors.append(f"selection '{name}' uses unknown field '{base}'")
        if modifier is not None and modifier not in MODIFIERS:
            errors.append(f"selection '{name}' field '{base}' has unsupported modifier '{modifier}'")
        values = value if isinstance(value, list) else [value]
        if not values:
            errors.append(f"selection '{name}' field '{base}' has an empty value list")
        for v in values:
            if not isinstance(v, _SCALARS):
                errors.append(f"selection '{name}' field '{base}' has non-scalar value {v!r}")


def _tokenize(condition: str, errors: list[str]) -> list[str]:
    tokens, pos = [], 0
    text = condition.strip()
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            errors.append(f"condition has an invalid character near '{text[pos:pos + 10]}'")
            return []
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


def _check_condition(condition: Any, selections: set[str], errors: list[str]) -> None:
    """Grammar: expr := term (OR term)* ; term := factor (AND factor)* ;
    factor := NOT factor | '(' expr ')' | selection_name. Operators are case-insensitive."""
    if not isinstance(condition, str) or not condition.strip():
        errors.append("detection.condition must be a non-empty string")
        return
    tokens = _tokenize(condition, errors)
    if not tokens:
        return
    i = 0

    def peek() -> str | None:
        return tokens[i] if i < len(tokens) else None

    def factor() -> None:
        nonlocal i
        tok = peek()
        if tok is None:
            errors.append("condition ends unexpectedly")
            return
        if tok.lower() == "not":
            i += 1
            factor()
        elif tok == "(":
            i += 1
            expr()
            if peek() != ")":
                errors.append("condition has an unclosed '('")
                return
            i += 1
        elif tok.lower() in _OPERATORS or tok == ")":
            errors.append(f"condition has unexpected '{tok}'")
            i += 1
        else:
            if tok not in selections:
                errors.append(f"condition references undefined selection '{tok}'")
            i += 1

    def term() -> None:
        nonlocal i
        factor()
        while peek() is not None and peek().lower() == "and":
            i += 1
            factor()

    def expr() -> None:
        nonlocal i
        term()
        while peek() is not None and peek().lower() == "or":
            i += 1
            term()

    expr()
    if i < len(tokens) and not errors:
        errors.append(f"condition has trailing token '{tokens[i]}'")


def validate_rule_dict(d: Any) -> ValidationResult:
    errors: list[str] = []
    if not isinstance(d, dict):
        return ValidationResult(False, ["rule must be a JSON object"])
    missing = [k for k in _REQUIRED if k not in d]
    if missing:
        return ValidationResult(False, [f"missing required fields: {', '.join(missing)}"])

    if not isinstance(d["rule_id"], str) or not d["rule_id"].strip():
        errors.append("rule_id must be a non-empty string")
    if isinstance(d["round"], bool) or not isinstance(d["round"], int) or d["round"] < 0:
        errors.append("round must be an integer >= 0")
    if not isinstance(d["agent_id"], str) or not _AGENT_RE.match(d["agent_id"]):
        errors.append("agent_id must look like 'blue_0' .. 'blue_4'")
    if not isinstance(d["title"], str) or not d["title"].strip():
        errors.append("title must be a non-empty string")
    if d["level"] not in LEVELS:
        errors.append(f"level must be one of {sorted(LEVELS)}")
    conf = d["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        errors.append("confidence must be a number in [0, 1]")
    rationale = d.get("rationale", "")
    if not isinstance(rationale, str) or len(rationale) > MAX_RATIONALE_CHARS:
        errors.append(f"rationale must be a string of at most {MAX_RATIONALE_CHARS} characters")

    logsource = d["logsource"]
    if not isinstance(logsource, dict) or logsource.get("category") not in EVENT_CATEGORIES:
        errors.append(f"logsource.category must be one of {sorted(EVENT_CATEGORIES)}")

    detection = d["detection"]
    if not isinstance(detection, dict):
        errors.append("detection must be an object with selections and a condition")
    else:
        selections = {k: v for k, v in detection.items() if k != "condition"}
        if not selections:
            errors.append("detection needs at least one named selection")
        for name, sel in selections.items():
            if not _NAME_RE.match(str(name)) or str(name).lower() in _OPERATORS:
                errors.append(f"selection name '{name}' is not a valid identifier")
            _check_selection(str(name), sel, errors)
        if "condition" not in detection:
            errors.append("detection.condition is missing")
        else:
            _check_condition(detection["condition"], set(selections), errors)
    return ValidationResult(not errors, errors)


def validate_rule(rule: Rule) -> ValidationResult:
    return validate_rule_dict(rule.to_dict())


def rule_validity(rules: list[dict[str, Any]]) -> float:
    """RuleValidity in [0, 1]: fraction of emitted rules that pass validation (paper Eq. 2). Empty -> 0.0."""
    if not rules:
        return 0.0
    return sum(validate_rule_dict(r).valid for r in rules) / len(rules)
