"""Export a validated Rule to a Sigma rule dict and cross-check it with pySigma.

Our own validator (validator.py) is the gate used in training. This module is the "is it really
Sigma?" check for the paper's deployability claim; it is not on the hot path.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sigma.rule import SigmaRule

from src.rules.schema import Rule

_NAMESPACE = uuid.UUID("6f1c0d2e-3b7a-4c55-9a40-2f0e5c6b7d11")


_OPERATOR_RE = re.compile(r"\b(and|or|not)\b", re.IGNORECASE)


def to_sigma_dict(rule: Rule) -> dict[str, Any]:
    # pySigma only accepts lowercase boolean operators; our grammar is case-insensitive.
    detection = dict(rule.detection)
    detection["condition"] = _OPERATOR_RE.sub(lambda m: m.group(1).lower(), str(detection["condition"]))
    return {
        "title": rule.title,
        "id": str(uuid.uuid5(_NAMESPACE, rule.rule_id)),
        "status": "experimental",
        "description": rule.rationale or rule.title,
        "logsource": {"category": rule.logsource["category"]},
        "detection": detection,
        "level": rule.level,
        "falsepositives": ["Unknown"],
        "tags": [f"cc4.confidence_{rule.confidence:.2f}", f"cc4.{rule.agent_id}", f"cc4.round_{rule.round}"],
    }


def pysigma_errors(rule: Rule) -> list[str]:
    """Parse with pySigma; returns a list of error strings (empty = pySigma accepts it)."""
    try:
        parsed = SigmaRule.from_dict(to_sigma_dict(rule))
        # pySigma defers condition checking until each condition is parsed.
        for condition in parsed.detection.parsed_condition:
            condition.parse()
    except Exception as exc:  # pySigma raises several exception types for malformed rules
        return [f"{type(exc).__name__}: {exc}"]
    return [str(e) for e in parsed.errors]
