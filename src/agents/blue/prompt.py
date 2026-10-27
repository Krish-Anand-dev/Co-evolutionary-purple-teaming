"""Prompt builder for the Blue rule-proposal call (once per round, Decision D1 mode B).

The prompt carries: task, rule schema, the Blue-visible field vocabulary, few-shot VALID rules, the
previous round's alerts, and observable feedback. Blue never sees ground truth: `feedback` must be
built only from things Blue can observe (e.g. which hosts needed Restore, which alerts led to no
confirmed compromise, reward penalties). Never put label_red / source_action / source_agent here.
"""
from __future__ import annotations

import json
from typing import Any

from src.rules.schema import EVENT_CATEGORIES, HIDDEN_FIELDS, LEVELS, MAX_RATIONALE_CHARS, VISIBLE_FIELDS

FEW_SHOT: list[dict[str, Any]] = [
    {
        "title": "Connections to decoy service",
        "level": "high",
        "logsource": {"category": "network_connection"},
        "detection": {"decoy_hit": {"is_decoy": True}, "condition": "decoy_hit"},
        "confidence": 0.9,
        "rationale": "Green users never touch decoys, so any access is suspicious.",
    },
    {
        "title": "Elevated shell spawned by network service",
        "level": "high",
        "logsource": {"category": "process_creation"},
        "detection": {
            "elevated": {"privilege": "elevated"},
            "from_service": {"parent_process|contains": "d"},
            "condition": "elevated and from_service",
        },
        "confidence": 0.7,
        "rationale": "Privilege escalation under a daemon parent is rare in normal work.",
    },
    {
        "title": "Probe of common service ports",
        "level": "medium",
        "logsource": {"category": "network_connection"},
        "detection": {"ports": {"dst_port": [22, 80, 443, 445, 3389]}, "condition": "ports"},
        "confidence": 0.4,
        "rationale": "Scanning touches many service ports; may also hit benign traffic.",
    },
]

_FORBIDDEN_IN_PROMPT = tuple(HIDDEN_FIELDS)


def _fmt_alerts(alerts: list[dict[str, Any]], limit: int = 15) -> str:
    if not alerts:
        return "(none)"
    shown = alerts[:limit]
    lines = [f"- rule={a.get('rule_id')} host={a.get('host_id')} step={a.get('step')} level={a.get('level')}" for a in shown]
    if len(alerts) > limit:
        lines.append(f"- ... and {len(alerts) - limit} more")
    return "\n".join(lines)


def _nest(rule: dict[str, Any]) -> dict[str, Any]:
    """Few-shot rule in the nested layout: selections and condition as rule-level keys, selections first."""
    det = rule["detection"]
    out: dict[str, Any] = {k: v for k, v in rule.items() if k != "detection"}
    ordered = {k: out[k] for k in ("title", "level", "logsource") if k in out}
    ordered["selections"] = {k: v for k, v in det.items() if k != "condition"}
    ordered["condition"] = det["condition"]
    ordered.update({k: v for k, v in out.items() if k not in ordered})
    return ordered


def build_prompt(round_ctx: dict[str, Any], max_rules: int = 5, repair_errors: list[str] | None = None,
                 nested: bool = False) -> str:
    """nested=True shows the layout with `selections` before `condition` at rule level (pairs with the nested
    schema in schema.py; repair.extract_rule_objects converts it back to a `detection` block)."""
    agent_id = round_ctx.get("agent_id", "blue_0")
    previous = round_ctx.get("previous_rules", [])
    feedback = round_ctx.get("feedback", [])
    if nested:
        layout = {
            "title": "short human-readable title",
            "level": "low|medium|high",
            "logsource": {"category": "one of " + ", ".join(sorted(EVENT_CATEGORIES))},
            "selections": {"<selection_name>": {"<field>": "<value or [values]>"}},
            "condition": "selection_name AND NOT other",
            "confidence": "number 0..1",
            "rationale": f"<= {MAX_RATIONALE_CHARS} chars",
        }
        examples = [_nest(r) for r in FEW_SHOT]
    else:
        layout = {
            "title": "short human-readable title",
            "level": "low|medium|high",
            "logsource": {"category": "one of " + ", ".join(sorted(EVENT_CATEGORIES))},
            "detection": {"<selection_name>": {"<field>": "<value or [values]>"}, "condition": "selection_name AND NOT other"},
            "confidence": "number 0..1",
            "rationale": f"<= {MAX_RATIONALE_CHARS} chars",
        }
        examples = FEW_SHOT
    parts = [
        f"You are {agent_id}, a SOC detection engineer defending one network zone. "
        f"Write up to {max_rules} detection rules as JSON for the next round.",
        "RULE FORMAT (JSON object per rule, no extra keys needed beyond these):",
        json.dumps(layout, indent=1),
        "RULES OF THE FORMAT:",
        f"- level is one of {sorted(LEVELS)}.",
        "- Selection fields are ANDed; a list of values for one field is ORed.",
        "- Field modifiers allowed: field|contains, field|startswith, field|endswith.",
        "- condition uses only selection names, AND, OR, NOT and parentheses.",
        "- Use ONLY these fields: " + ", ".join(sorted(VISIBLE_FIELDS)) + ".",
        "- Do not invent fields. Do not use ids, rule_id, round or agent_id (they are added for you).",
        "EXAMPLES OF VALID RULES:",
        json.dumps(examples, indent=1),
        "ALERTS YOUR CURRENT RULES FIRED LAST ROUND:",
        _fmt_alerts(round_ctx.get("last_alerts", [])),
        "OBSERVABLE FEEDBACK (what you could see, not ground truth):",
        "\n".join(f"- {line}" for line in feedback) if feedback else "(none)",
        "YOUR CURRENT RULE TITLES:",
        "\n".join(f"- {r.get('title')}" for r in previous) if previous else "(none yet)",
        "Prefer rules that are precise: green users generate benign traffic, so rules that fire on everything are penalised.",
        'Answer with ONLY a JSON object: {"rules": [ ... ]}.',
    ]
    if repair_errors:
        parts.append("YOUR PREVIOUS ANSWER HAD THESE PROBLEMS, FIX THEM:")
        parts.extend(f"- {e}" for e in repair_errors[:10])
    prompt = "\n".join(parts)
    # Guard: the only legitimate mention of hidden names would be a leak. Fail loudly, never silently.
    for name in _FORBIDDEN_IN_PROMPT:
        if name in prompt:
            raise ValueError(f"ground-truth field '{name}' leaked into the Blue prompt")
    return prompt
