"""Load rule sets from JSON files (static baseline rules, saved agent rule sets)."""
from __future__ import annotations

import json
from pathlib import Path

from src.rules.schema import Rule
from src.rules.validator import validate_rule_dict


def load_rules(path: str | Path, strict: bool = True) -> list[Rule]:
    """Read a JSON list of rule objects. strict=True raises on the first invalid rule; otherwise skips it."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of rules")
    rules: list[Rule] = []
    for d in data:
        result = validate_rule_dict(d)
        if result.valid:
            rules.append(Rule.from_dict(d))
        elif strict:
            raise ValueError(f"{path}: rule {d.get('rule_id') if isinstance(d, dict) else d!r} invalid: {result.errors}")
    return rules
