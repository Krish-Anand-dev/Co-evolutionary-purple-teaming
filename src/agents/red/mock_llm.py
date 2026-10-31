"""Mock LLM for the Red planner (T20): valid plans plus configurable faults, no GPU needed.

A FAULT MODEL, not a language model. Numbers measured with it test the parsing, validation, retry and fallback path,
never how good a real LLM's plans are (see scripts/run_llm_red.py --llama-server for that).
"""
from __future__ import annotations

import json
import random
from typing import Any

from src.agents.red.plan import GOALS, SCANS

DEFAULT_FAULT_WEIGHTS = {"ok": 60, "fenced": 8, "prose_prefix": 6, "out_of_range": 8, "missing_field": 6,
                         "unknown_field": 4, "bad_enum": 4, "no_json": 4}


class MockRedLLM:
    def __init__(self, seed: int = 0, fault_weights: dict[str, int] | None = None, repair_success: float = 0.7):
        self.rng = random.Random(seed)
        self.weights = fault_weights or DEFAULT_FAULT_WEIGHTS
        self.repair_success = repair_success
        self.calls = 0

    def _plan(self) -> dict[str, Any]:
        r = self.rng
        return {"goal": r.choice(GOALS), "scan": r.choice(SCANS), "probe_decoys": round(r.random(), 2),
                "prioritise_servers": r.random() < 0.5, "impact_bias": round(r.random(), 2),
                "degrade_share": round(r.random(), 2), "rationale": "Mock plan."}

    def generate(self, prompt: str, schema: dict | None = None) -> tuple[str, dict[str, Any]]:
        self.calls += 1
        repair = "PREVIOUS ANSWER HAD PROBLEMS" in prompt
        fault = "ok" if (repair and self.rng.random() < self.repair_success) else self.rng.choices(
            list(self.weights), weights=list(self.weights.values()))[0]
        plan = self._plan()
        if fault == "fenced":
            text = f"```json\n{json.dumps(plan)}\n```"
        elif fault == "prose_prefix":
            text = f"Here is my plan: {json.dumps(plan)} Good luck!"
        elif fault == "out_of_range":
            plan["impact_bias"] = 1.7
            text = json.dumps(plan)
        elif fault == "missing_field":
            del plan["scan"]
            text = json.dumps(plan)
        elif fault == "unknown_field":
            plan["attack_everything"] = True
            text = json.dumps(plan)
        elif fault == "bad_enum":
            plan["goal"] = "destroy_all"
            text = json.dumps(plan)
        elif fault == "no_json":
            text = "I would attack the servers first."
        else:
            text = json.dumps(plan)
        return text, {"model": "mock", "fault": fault, "latency_s": 0.0, "tokens_in": len(prompt) // 4,
                      "tokens_out": len(text) // 4}
