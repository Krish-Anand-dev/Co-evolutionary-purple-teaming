"""Round-level plan for the LLM Red agent (T20): schema, strict validator, and the compiler that turns a plan into the
probability table CAGE-4's FiniteStateRedAgent plays from.

Decision D1: the LLM acts once per round. It never picks individual actions, so every step is played by the cheap FSM
executor and no action can be illegal; the LLM only chooses a strategy within the fields below. The validator is
deliberately strict: a plan with any out-of-range or missing field is rejected as a whole and the round falls back to
CAGE-4's default scripted Red (counted as an invalid plan).

Table column order (same as src/agents/red/scripted.py):
    [DiscoverRemoteSystems, AggressiveServiceDiscovery, StealthServiceDiscovery, DiscoverDeception,
     ExploitRemoteService, PrivilegeEscalate, Impact, DegradeServices, Withdraw]
Withdraw is never offered (it can strand the agent, see docs/red-strategies.md).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

GOALS = ("stealth_recon", "fast_impact", "decoy_evasion", "balanced")
SCANS = ("aggressive", "stealthy", "mixed")
MAX_RATIONALE = 300

FIELDS = ("goal", "scan", "probe_decoys", "prioritise_servers", "impact_bias", "degrade_share", "rationale")


@dataclass(frozen=True)
class RedPlan:
    goal: str
    scan: str
    probe_decoys: float      # 0..1  how much to run DiscoverDeception before exploiting
    prioritise_servers: bool
    impact_bias: float       # 0..1  on rooted hosts: 1 = go straight for Impact/Degrade, 0 = keep discovering
    degrade_share: float     # 0..1  of that effort, share spent on DegradeServices instead of Impact
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_json_schema() -> dict[str, Any]:
    """Structure only (for llama-server constrained decoding); ranges are checked again by `validate_plan`."""
    return {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "enum": list(GOALS)},
            "scan": {"type": "string", "enum": list(SCANS)},
            "probe_decoys": {"type": "number", "minimum": 0, "maximum": 1},
            "prioritise_servers": {"type": "boolean"},
            "impact_bias": {"type": "number", "minimum": 0, "maximum": 1},
            "degrade_share": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
        },
        "required": list(FIELDS),
    }


def extract_json_object(text: str) -> dict | None:
    """The first {...} object in the text (models sometimes add a code fence or a sentence), or None."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_plan(obj: Any) -> tuple[RedPlan | None, list[str]]:
    """(plan, []) if valid, else (None, [reasons]). Unknown extra keys are errors too (they signal a confused answer)."""
    if not isinstance(obj, dict):
        return None, ["answer is not a JSON object"]
    errors: list[str] = []
    for key in FIELDS:
        if key not in obj:
            errors.append(f"missing field {key}")
    for key in obj:
        if key not in FIELDS:
            errors.append(f"unknown field {key}")
    if errors:
        return None, errors
    if obj["goal"] not in GOALS:
        errors.append(f"goal must be one of {list(GOALS)}")
    if obj["scan"] not in SCANS:
        errors.append(f"scan must be one of {list(SCANS)}")
    for key in ("probe_decoys", "impact_bias", "degrade_share"):
        v = obj[key]
        if not _is_number(v) or not 0.0 <= v <= 1.0:
            errors.append(f"{key} must be a number in [0, 1]")
    if not isinstance(obj["prioritise_servers"], bool):
        errors.append("prioritise_servers must be true or false")
    if not isinstance(obj["rationale"], str) or len(obj["rationale"]) > MAX_RATIONALE:
        errors.append(f"rationale must be text of at most {MAX_RATIONALE} characters")
    if errors:
        return None, errors
    return RedPlan(goal=obj["goal"], scan=obj["scan"], probe_decoys=float(obj["probe_decoys"]),
                   prioritise_servers=obj["prioritise_servers"], impact_bias=float(obj["impact_bias"]),
                   degrade_share=float(obj["degrade_share"]), rationale=obj["rationale"]), []


def parse_plan(text: str) -> tuple[RedPlan | None, list[str]]:
    obj = extract_json_object(text)
    if obj is None:
        return None, ["no JSON object found in the answer"]
    return validate_plan(obj)


def _normalise(row: list[float | None]) -> list[float | None]:
    """Drop zero weights (None = action not offered) and rescale so the offered actions sum to 1."""
    row = [None if (v is None or v <= 1e-9) else v for v in row]
    total = sum(v for v in row if v is not None)
    return [None if v is None else v / total for v in row]


def compile_plan(plan: RedPlan) -> tuple[dict[str, list[float | None]], dict[str, float]]:
    """Plan -> (state transition probability table, host-state priority list) for the FSM executor."""
    aggr = {"aggressive": 1.0, "stealthy": 0.0, "mixed": 0.5}[plan.scan]
    ste = 1.0 - aggr
    probe = plan.probe_decoys
    ib, ds = plan.impact_bias, plan.degrade_share
    impact, degrade = ib * (1 - ds), ib * ds
    discover = max(1.0 - ib, 0.05)

    n = None
    table = {
        "K":  [0.2, 0.8 * aggr, 0.8 * ste, n, n, n, n, n, n],
        "KD": [n, aggr, ste, n, n, n, n, n, n],
        "S":  [0.15, n, n, 0.05 + 0.6 * probe, 0.8 - 0.6 * probe, n, n, n, n],
        "SD": [n, n, n, 0.1 * probe, 1.0 - 0.1 * probe, n, n, n, n],
        "U":  [0.2, n, n, n, n, 0.8, n, n, n],
        "UD": [n, n, n, n, n, 1.0, n, n, n],
        "R":  [discover, n, n, n, n, n, impact, degrade, n],
        "RD": [discover, n, n, n, n, n, impact, degrade, n],
    }
    table = {state: _normalise(row) for state, row in table.items()}
    # states hosts are chosen from: push forward when impact_bias is high, keep exploring when it is low
    push = 5 + 25 * ib
    priority = {"K": 25 - 15 * ib, "KD": 25 - 15 * ib, "S": 20, "SD": 10, "U": push, "UD": push / 2, "R": push / 2, "RD": 5}
    total = sum(priority.values())
    priority = {k: 100 * v / total for k, v in priority.items()}
    return table, priority
