"""Rule dataclass and the event vocabulary (Interface Contract sections 2-3, DRAFT until D2/T12)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EVENT_CATEGORIES = frozenset({"process_creation", "network_connection", "service_event"})
LEVELS = frozenset({"low", "medium", "high"})

# Blue-visible event fields. A rule may only reference these.
VISIBLE_FIELDS = frozenset({
    "event_id", "step", "blue_agent", "host_id", "subnet", "zone", "category",
    "process_name", "parent_process", "privilege", "src_ip", "dst_ip", "dst_port",
    "protocol", "service_name", "is_decoy",
})

# Ground truth. Blue must never see or reference these.
HIDDEN_FIELDS = frozenset({"label_red", "source_action", "source_agent"})

# Sigma-style field modifiers we accept (field|modifier).
MODIFIERS = frozenset({"contains", "startswith", "endswith"})

MAX_RATIONALE_CHARS = 300


@dataclass
class Rule:
    rule_id: str
    round: int
    agent_id: str
    title: str
    level: str
    logsource: dict[str, Any]
    detection: dict[str, Any]
    confidence: float
    rationale: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        known = {"rule_id", "round", "agent_id", "title", "level", "logsource",
                 "detection", "confidence", "rationale"}
        return cls(
            rule_id=d["rule_id"], round=d["round"], agent_id=d["agent_id"],
            title=d["title"], level=d["level"], logsource=d["logsource"],
            detection=d["detection"], confidence=d["confidence"],
            rationale=d.get("rationale", ""),
            extra={k: v for k, v in d.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id, "round": self.round, "agent_id": self.agent_id,
            "title": self.title, "level": self.level, "logsource": self.logsource,
            "detection": self.detection, "confidence": self.confidence,
            "rationale": self.rationale,
        }
