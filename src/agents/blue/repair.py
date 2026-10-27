"""Turn raw LLM text into candidate rule dicts, tolerating common formatting faults.

Two stages, kept separate so we can report validity before and after cosmetic fixes:
  extract_rule_objects(text) -> list[dict]   find JSON objects (fences, prose, trailing commas, truncation)
  normalise_rule(d)          -> dict         cosmetic fixes only (case, clamping, length); never invents fields
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.rules.schema import MAX_RATIONALE_CHARS

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
# A value ends (} ] " digit true/false/null) and the next line starts a new key without a comma between.
_MISSING_COMMA_RE = re.compile(r'([}\]"\d]|true|false|null)(\s*\n\s*")')


def _balanced_objects(text: str) -> list[str]:
    """Top-level {...} substrings, string-aware. A truncated final object is dropped."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(text[start:i + 1])
                start = None
    return out


def _loads(chunk: str) -> Any | None:
    """Strict parse first; only if that fails try the two common LLM JSON slips (never alters valid JSON)."""
    no_trailing = _TRAILING_COMMA_RE.sub(r"\1", chunk)
    for candidate in (chunk, no_trailing, _MISSING_COMMA_RE.sub(r"\1,\2", no_trailing)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def flatten_nested_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Nested layout {selections: {...}, condition: "..."} -> Sigma-style detection {name: {...}, condition: "..."}.
    Structural only, nothing is added or dropped. Left untouched if there is already a `detection`, no `selections`
    mapping, or a selection is itself named "condition" (that would collide)."""
    selections = rule.get("selections")
    if "detection" in rule or not isinstance(selections, dict) or "condition" in selections:
        return rule
    out = {k: v for k, v in rule.items() if k not in ("selections", "condition")}
    detection = dict(selections)
    if "condition" in rule:
        detection["condition"] = rule["condition"]
    out["detection"] = detection
    return out


def extract_rule_objects(text: str) -> list[dict[str, Any]]:
    """All rule-shaped objects in `text`. A wrapper like {"rules": [...]} is unwrapped; nested-layout rules are
    converted to the flat `detection` layout."""
    fenced = _FENCE_RE.findall(text)
    body = "\n".join(fenced) if fenced else text
    rules: list[dict[str, Any]] = []
    for chunk in _balanced_objects(body):
        obj = _loads(chunk)
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("rules"), list):
            rules.extend(flatten_nested_rule(r) for r in obj["rules"] if isinstance(r, dict))
        elif "detection" in obj or "title" in obj:
            rules.append(flatten_nested_rule(obj))
    return rules


def normalise_rule(d: dict[str, Any]) -> dict[str, Any]:
    """Cosmetic, lossless-in-meaning fixes. Does not add or rename fields."""
    out = dict(d)
    # Seen with Gemma 4: "condition" written next to "detection" instead of inside it. Same content, moved.
    detection = out.get("detection")
    if isinstance(detection, dict) and "condition" not in detection and isinstance(out.get("condition"), str):
        out["detection"] = {**detection, "condition": out.pop("condition")}
    if isinstance(out.get("level"), str):
        out["level"] = out["level"].strip().lower()
    conf = out.get("confidence")
    if isinstance(conf, str):
        try:
            conf = float(conf.strip().rstrip("%")) / (100.0 if conf.strip().endswith("%") else 1.0)
        except ValueError:
            conf = None
        if conf is not None:
            out["confidence"] = conf
    if isinstance(out.get("confidence"), (int, float)) and not isinstance(out["confidence"], bool):
        out["confidence"] = min(1.0, max(0.0, float(out["confidence"])))
    if isinstance(out.get("rationale"), str):
        out["rationale"] = out["rationale"][:MAX_RATIONALE_CHARS]
    return out
