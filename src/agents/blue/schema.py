"""JSON schema for constrained decoding of the Blue rule-proposal answer (llama-server `response_format`).

Two variants:
  basic  (default)  constrains STRUCTURE only: valid JSON, the right keys, `condition` inside `detection`, enum
                    values for level and category. Measured 27/28-Oct-2026 on Gemma 4: WORSE than no schema
                    (the model invented extra "selections" such as `condition_logic`, and answers got longer).
  strict            additionally restricts selection KEYS to the Blue-visible event fields (optionally with a
                    |contains / |startswith / |endswith modifier). Hidden ground-truth fields cannot be generated.
The validator in src/rules/validator.py remains the single source of truth for what a valid rule is.
"""
from __future__ import annotations

from typing import Any

from src.rules.schema import EVENT_CATEGORIES, LEVELS, MODIFIERS, VISIBLE_FIELDS

_SCALAR = {"type": ["string", "number", "boolean"]}
_VALUE = {"anyOf": [_SCALAR, {"type": "array", "items": _SCALAR, "minItems": 1}]}


def _field_key_pattern() -> str:
    fields = "|".join(sorted(VISIBLE_FIELDS))
    mods = "|".join(sorted(MODIFIERS))
    return rf"^({fields})(\|({mods}))?$"


def _selection(strict: bool) -> dict[str, Any]:
    if strict:
        return {"type": "object", "patternProperties": {_field_key_pattern(): _VALUE},
                "additionalProperties": False, "minProperties": 1}
    return {"type": "object", "additionalProperties": _VALUE}


def rule_json_schema(max_rules: int = 5, strict_fields: bool = False, nested: bool = False) -> dict[str, Any]:
    """nested=True writes `selections` and `condition` as rule-level keys, selections FIRST, so the model defines
    the selections before it writes the condition that names them (the flat layout puts `condition` first because
    fixed properties precede additionalProperties; measured 28-Oct: the model then invents a fake selection).
    repair.extract_rule_objects converts the nested layout back into the Sigma-style `detection` block."""
    head = {
        "title": {"type": "string"},
        "level": {"type": "string", "enum": sorted(LEVELS)},
        "logsource": {
            "type": "object",
            "properties": {"category": {"type": "string", "enum": sorted(EVENT_CATEGORIES)}},
            "required": ["category"],
        },
    }
    tail = {"confidence": {"type": "number", "minimum": 0, "maximum": 1}, "rationale": {"type": "string"}}
    if nested:
        rule = {
            "type": "object",
            "properties": {
                **head,
                "selections": {"type": "object", "additionalProperties": _selection(strict_fields), "minProperties": 1},
                "condition": {"type": "string"},
                **tail,
            },
            "required": ["title", "level", "logsource", "selections", "condition", "confidence", "rationale"],
        }
    else:
        rule = {
            "type": "object",
            "properties": {
                **head,
                "detection": {
                    "type": "object",
                    "properties": {"condition": {"type": "string"}},
                    "required": ["condition"],
                    "additionalProperties": _selection(strict_fields),
                },
                **tail,
            },
            "required": ["title", "level", "logsource", "detection", "confidence", "rationale"],
        }
    return {
        "type": "object",
        "properties": {"rules": {"type": "array", "items": rule, "minItems": 1, "maxItems": max_rules}},
        "required": ["rules"],
    }
