"""Event type shared by the telemetry bridge, the rule executor and the labeler.

Two views of the same event:
  visible()  only the Blue-visible fields (the event schema in docs/contract-v1.md section 3, DRAFT until D2)
  to_log()   visible fields plus the hidden ones, for experiment logs and the labeler. Never given to Blue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.rules.schema import HIDDEN_FIELDS, VISIBLE_FIELDS


@dataclass
class Event:
    # ---- Blue-visible ----
    event_id: str
    step: int
    blue_agent: str
    host_id: str
    category: str                       # process_creation | network_connection | service_event
    subnet: str | None = None
    zone: str | None = None
    process_name: str | None = None
    parent_process: str | None = None
    privilege: str | None = None        # user | elevated
    src_ip: str | None = None
    dst_ip: str | None = None
    dst_port: int | None = None
    protocol: str | None = None
    service_name: str | None = None
    is_decoy: bool = False
    # ---- hidden (never shown to Blue) ----
    label_red: int | None = None        # ground truth; filled by the labeler (T21), not by the bridge
    source_action: str | None = None
    source_agent: str | None = None
    provenance: str = "native"          # native | enriched | synthetic
    enriched_fields: tuple[str, ...] = field(default_factory=tuple)

    def visible(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in sorted(VISIBLE_FIELDS)}

    def to_log(self) -> dict[str, Any]:
        out = self.visible()
        out.update({name: getattr(self, name) for name in sorted(HIDDEN_FIELDS)})
        out["provenance"] = self.provenance
        out["enriched_fields"] = list(self.enriched_fields)
        return out
