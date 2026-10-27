"""Response playbook: alerts -> CAGE-4 Blue actions (Analyse / Remove / Restore).

Deterministic and parameterised so every condition uses the same playbook (protocol rule 2).
Actions come back as (action_name, host_id) pairs; mapping to concrete CybORG action objects
and host-slot indices is the integration layer's job (T27).

Policy per host per step, using the highest alert level seen on that host:
  low     -> no action (logged only)
  medium  -> Analyse
  high    -> Remove
  and if the host was already Removed `restore_after` consecutive steps ago and alerts persist -> Restore
A host is not acted on again until `cooldown` steps have passed (CAGE-4 actions take 2-5 ticks).
Restore is expensive for availability, so it is only used for persistent high alerts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from src.rules.executor import Alert

_LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass
class PlaybookParams:
    min_confidence: float = 0.0
    restore_after: int = 2   # consecutive high-alert Removes on a host before escalating to Restore
    cooldown: int = 3        # steps before the same host can be actioned again


@dataclass
class ResponsePlaybook:
    params: PlaybookParams = field(default_factory=PlaybookParams)
    _last_action_step: dict = field(default_factory=dict, init=False)
    _removes: dict = field(default_factory=dict, init=False)

    def reset(self) -> None:
        self._last_action_step.clear()
        self._removes.clear()

    def decide(self, step: int, alerts: Iterable[Alert]) -> list[tuple[str, object]]:
        worst: dict = {}
        for a in alerts:
            if a.confidence < self.params.min_confidence or a.host_id is None:
                continue
            if a.host_id not in worst or _LEVEL_RANK[a.level] > _LEVEL_RANK[worst[a.host_id]]:
                worst[a.host_id] = a.level

        actions: list[tuple[str, object]] = []
        for host in sorted(worst, key=str):  # sorted -> deterministic output order
            level = worst[host]
            if level == "low":
                continue
            last = self._last_action_step.get(host)
            if last is not None and step - last < self.params.cooldown:
                continue
            if level == "medium":
                actions.append(("Analyse", host))
            else:
                removes = self._removes.get(host, 0)
                if removes >= self.params.restore_after:
                    actions.append(("Restore", host))
                    self._removes[host] = 0
                else:
                    actions.append(("Remove", host))
                    self._removes[host] = removes + 1
            self._last_action_step[host] = step
        return actions
