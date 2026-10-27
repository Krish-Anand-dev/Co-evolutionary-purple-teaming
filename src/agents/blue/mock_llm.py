"""Mock LLM for developing and testing the Blue agent without a GPU.

It produces plausible rule JSON and injects formatting / schema faults at configurable rates. It is a
FAULT MODEL, not a language model: numbers measured with it test our parsing + validation pipeline,
never the quality of a real LLM. Real validity rates must come from OllamaClient runs (T09 / T18 follow-up).
"""
from __future__ import annotations

import json
import random
from typing import Any

DEFAULT_FAULT_WEIGHTS = {
    "ok": 40, "fenced": 12, "prose_prefix": 8, "trailing_comma": 6, "truncated": 5,
    "unknown_field": 8, "hidden_field": 3, "bad_condition": 6, "level_case": 4, "conf_percent": 3,
    "no_json": 5,
}

_TEMPLATES = [
    ("Probe of SSH or RDP ports", "network_connection", "medium", {"dst_port": [22, 3389]}),
    ("Decoy service touched", "network_connection", "high", {"is_decoy": True}),
    ("Elevated process on server", "process_creation", "high", {"privilege": "elevated", "zone": "restricted"}),
    ("Shell-like process from daemon", "process_creation", "medium", {"process_name|contains": "sh", "parent_process|endswith": "d"}),
    ("Outbound to port 4444", "network_connection", "high", {"dst_port": 4444}),
    ("Service stopped", "service_event", "high", {"service_name|contains": "http"}),
]


class MockLLMClient:
    def __init__(self, seed: int = 0, fault_weights: dict[str, int] | None = None, repair_success: float = 0.7):
        self.rng = random.Random(seed)
        self.weights = fault_weights or DEFAULT_FAULT_WEIGHTS
        self.repair_success = repair_success
        self.calls = 0

    def _rules(self, n: int) -> list[dict[str, Any]]:
        out = []
        for title, cat, level, fields in self.rng.sample(_TEMPLATES, k=min(n, len(_TEMPLATES))):
            out.append({
                "title": title, "level": level, "logsource": {"category": cat},
                "detection": {"sel": dict(fields), "condition": "sel"},
                "confidence": round(self.rng.uniform(0.3, 0.95), 2),
                "rationale": f"{title}: unusual for green users.",
            })
        return out

    def generate(self, prompt: str, schema: dict | None = None) -> tuple[str, dict[str, Any]]:
        self.calls += 1
        is_repair = "PREVIOUS ANSWER HAD" in prompt
        fault = "ok" if (is_repair and self.rng.random() < self.repair_success) else self.rng.choices(
            list(self.weights), weights=list(self.weights.values()))[0]
        rules = self._rules(self.rng.randint(1, 4))
        text = self._render(fault, rules)
        return text, {"model": "mock", "fault": fault, "latency_s": 0.0, "tokens_in": len(prompt) // 4,
                      "tokens_out": len(text) // 4}

    def _render(self, fault: str, rules: list[dict[str, Any]]) -> str:
        body = json.dumps({"rules": rules}, indent=1)
        if fault == "fenced":
            return f"```json\n{body}\n```"
        if fault == "prose_prefix":
            return f"Sure! Here are my proposed detection rules:\n{body}\nLet me know if you need changes."
        if fault == "trailing_comma":
            return body.replace("]\n}", ",]\n}")
        if fault == "truncated":
            return body[: int(len(body) * self.rng.uniform(0.4, 0.9))]
        if fault == "unknown_field":
            rules[0]["detection"]["sel"]["registry_key"] = "HKLM\\Run"
            return json.dumps({"rules": rules})
        if fault == "hidden_field":
            rules[0]["detection"]["sel"] = {"label_red": 1}
            return json.dumps({"rules": rules})
        if fault == "bad_condition":
            rules[0]["detection"]["condition"] = "sel AND missing_sel"
            return json.dumps({"rules": rules})
        if fault == "level_case":
            rules[0]["level"] = rules[0]["level"].upper()
            return json.dumps({"rules": rules})
        if fault == "conf_percent":
            rules[0]["confidence"] = f"{int(rules[0]['confidence'] * 100)}%"
            return json.dumps({"rules": rules})
        if fault == "no_json":
            return "I would recommend monitoring unusual port activity and decoy access."
        return body
