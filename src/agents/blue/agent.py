"""Blue LLM agent v1 (T18): one LLM proposal per round, a cheap executor + playbook acts each step.

Agent API (Interface Contract section 4):
  reset(seed); observe(events, step); act(step) -> actions; propose_rules(round_ctx) -> list[Rule]; update(trajectories)

Per round the LLM is called once, plus at most `max_repairs` repair calls when nothing valid came back
(Experiments tab assumes ~3 calls/round). If still nothing valid, the previous rules stay active (fallback).
The agent never reads ground-truth labels: events are passed to the executor, which only reads visible fields.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.agents.blue.llm_client import LLMClient
from src.agents.blue.prompt import build_prompt
from src.agents.blue.repair import extract_rule_objects, normalise_rule
from src.agents.blue.schema import rule_json_schema
from src.rules.executor import Alert, RuleExecutor
from src.rules.playbook import PlaybookParams, ResponsePlaybook
from src.rules.schema import Rule
from src.rules.validator import validate_rule_dict

log = logging.getLogger(__name__)


@dataclass
class ProposalStats:
    round: int
    llm_calls: int = 0
    objects_found: int = 0
    valid_raw: int = 0        # valid exactly as the LLM wrote it (after we stamp ids)
    valid_final: int = 0      # valid after cosmetic normalisation
    duplicates: int = 0
    fallback: bool = False
    errors: list[str] = field(default_factory=list)
    latency_s: float = 0.0


class BlueLLMAgent:
    def __init__(self, agent_id: str, client: LLMClient, max_rules: int = 5, max_repairs: int = 1,
                 max_active: int = 20, playbook: PlaybookParams | None = None, use_schema: bool = False,
                 strict_schema: bool = False, nested_schema: bool = False, prompt_hint: bool = False):
        self.agent_id, self.client = agent_id, client
        self.nested = nested_schema
        self.hint = prompt_hint
        constrained = use_schema or strict_schema or nested_schema
        self.schema = (rule_json_schema(max_rules, strict_fields=strict_schema, nested=nested_schema)
                       if constrained else None)
        self.max_rules, self.max_repairs, self.max_active = max_rules, max_repairs, max_active
        self.playbook = ResponsePlaybook(playbook or PlaybookParams())
        self.executor = RuleExecutor()
        self.active_rules: list[Rule] = []
        self.history: list[ProposalStats] = []
        self.trajectories: list[Any] = []
        self._step_alerts: list[Alert] = []

    # ---- per-step (cheap, no LLM) ----
    def reset(self, seed: int | None = None) -> None:
        self.playbook.reset()
        self._step_alerts = []

    def observe(self, events: list[dict[str, Any]], step: int) -> list[Alert]:
        self._step_alerts = self.executor.run(events)
        return self._step_alerts

    def act(self, step: int) -> list[tuple[str, object]]:
        return self.playbook.decide(step, self._step_alerts)

    def update(self, trajectories: list[Any]) -> None:
        self.trajectories.extend(trajectories)

    # ---- per-round (LLM) ----
    def _stamp(self, obj: dict[str, Any], rnd: int, idx: int) -> dict[str, Any]:
        stamped = {k: v for k, v in obj.items() if k not in {"rule_id", "round", "agent_id"}}
        stamped.update(rule_id=f"{self.agent_id}_r{rnd}_{idx}", round=rnd, agent_id=self.agent_id)
        return stamped

    @staticmethod
    def _signature(rule: Rule | dict[str, Any]) -> str:
        d = rule.to_dict() if isinstance(rule, Rule) else rule
        return json.dumps([d.get("logsource"), d.get("detection")], sort_keys=True, default=str)

    def _call(self, ctx: dict[str, Any], stats: ProposalStats, repair_errors: list[str] | None,
              start_idx: int) -> list[Rule]:
        text, meta = self.client.generate(
            build_prompt(ctx, self.max_rules, repair_errors, nested=self.nested, hint=self.hint), self.schema)
        stats.llm_calls += 1
        stats.latency_s += float(meta.get("latency_s") or 0.0)
        objects = extract_rule_objects(text)[: self.max_rules]
        stats.objects_found += len(objects)
        accepted: list[Rule] = []
        for offset, obj in enumerate(objects):
            stamped = self._stamp(obj, ctx["round"], start_idx + offset)
            if validate_rule_dict(stamped).valid:
                stats.valid_raw += 1
            fixed = normalise_rule(stamped)
            result = validate_rule_dict(fixed)
            if result.valid:
                stats.valid_final += 1
                accepted.append(Rule.from_dict(fixed))
            else:
                stats.errors.extend(result.errors)
        if not objects:
            stats.errors.append("no JSON rule objects found in the answer")
        return accepted

    def propose_rules(self, round_ctx: dict[str, Any]) -> list[Rule]:
        ctx = dict(round_ctx)
        ctx.setdefault("agent_id", self.agent_id)
        ctx.setdefault("previous_rules", [r.to_dict() for r in self.active_rules])
        stats = ProposalStats(round=ctx["round"])

        new_rules = self._call(ctx, stats, None, 0)
        repairs = 0
        while not new_rules and repairs < self.max_repairs:
            repairs += 1
            new_rules = self._call(ctx, stats, stats.errors[-10:], 100 * repairs)

        known = {self._signature(r) for r in self.active_rules}
        unique: list[Rule] = []
        for rule in new_rules:
            sig = self._signature(rule)
            if sig in known:
                stats.duplicates += 1
            else:
                known.add(sig)
                unique.append(rule)

        if unique:
            self.active_rules = (self.active_rules + unique)[-self.max_active:]
            self.executor = RuleExecutor(self.active_rules)
        else:
            stats.fallback = True   # keep previous rules unchanged
            log.warning("%s round %s: no new valid rule, keeping %d previous rules",
                        self.agent_id, ctx["round"], len(self.active_rules))
        self.history.append(stats)
        return unique
