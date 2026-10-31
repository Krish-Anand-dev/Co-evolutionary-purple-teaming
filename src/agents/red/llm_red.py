"""LLM Red agent v1 (T20): an LLM planner once per round + a cheap FSM executor (Decision D1).

RedPlanner     asks the LLM for a round plan (src/agents/red/plan.py), validates it strictly, retries once with the
               error list, and falls back to CAGE-4's default scripted Red when the answer is unusable. Past rounds are
               kept in a JSONL memory file and shown to the LLM, so it can see what worked and what failed.
PlannedRed     the executor CybORG instantiates (one per Red agent, all share the round's plan). It plays the compiled
               probability table and checks every action against the action space; an illegal one is replaced by Sleep.

Red only learns what Red can observe (its own action successes). Nothing from Blue's side, and nothing hidden, is
put in the prompt.
"""
from __future__ import annotations

import json
import logging
import pathlib
import time
from collections import Counter
from typing import Any

from CybORG.Agents.SimpleAgents.FiniteStateRedAgent import FiniteStateRedAgent
from CybORG.Simulator.Actions import Sleep

from src.agents.blue.llm_client import LLMClient
from src.agents.red.legality import is_legal
from src.agents.red.plan import GOALS, SCANS, RedPlan, compile_plan, parse_plan, plan_json_schema

log = logging.getLogger(__name__)

PROMPT_HEAD = """You plan the attacker (Red team) in a simulated enterprise network exercise (CAGE Challenge 4). \
The defender (Blue) is an automated system. Choose Red's strategy for the next round. Red plays 500 steps with a fixed \
set of actions; you do not pick single actions, you set the strategy below.

What Red can do: DiscoverRemoteSystems (find hosts), AggressiveServiceDiscovery (fast scan, very likely to raise an \
alert), StealthServiceDiscovery (slow scan, rarely raises an alert), DiscoverDeception (check whether a host runs \
decoy services; touching a decoy raises an alert and the exploit fails), ExploitRemoteService (gain a user shell), \
PrivilegeEscalate (gain root), Impact (stop a service, the main way to hurt the defender), DegradeServices (make normal \
users' work fail).

Answer with ONE JSON object and nothing else, with exactly these fields:
- goal: one of {goals}
- scan: one of {scans}  (aggressive = fast and loud, stealthy = slow and quiet, mixed = both)
- probe_decoys: number 0 to 1, how much to check for decoys before exploiting
- prioritise_servers: true or false
- impact_bias: number 0 to 1, on hosts where Red has root: 1 = go straight for Impact/Degrade, 0 = keep discovering
- degrade_share: number 0 to 1, share of that effort spent on DegradeServices instead of Impact
- rationale: one or two sentences, at most 300 characters
"""


class RedMemory:
    """Round-by-round JSONL memory of what Red tried and how it went."""

    def __init__(self, path: str | pathlib.Path | None = None):
        self.path = pathlib.Path(path) if path else None
        self.entries: list[dict[str, Any]] = []
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.entries.append(json.loads(line))

    def add(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def best_progress(self) -> float | None:
        vals = [e["outcome"]["progress"] for e in self.entries if "outcome" in e]
        return max(vals) if vals else None

    def render(self, last: int = 5) -> str:
        if not self.entries:
            return "No earlier rounds."
        best = self.best_progress()
        lines = []
        for e in self.entries[-last:]:
            p, o = e["plan"], e["outcome"]
            mark = " (best so far)" if o["progress"] == best else ""
            lines.append(
                f"round {e['round']}: plan goal={p['goal']} scan={p['scan']} probe_decoys={p['probe_decoys']:.2f} "
                f"impact_bias={p['impact_bias']:.2f} degrade_share={p['degrade_share']:.2f} "
                f"servers_first={p['prioritise_servers']} -> exploits ok {o['exploit_ok']}/{o['exploit_tries']}, "
                f"root gained {o['privesc_ok']}, Impact ok {o['impact_ok']}, Degrade ok {o['degrade_ok']}, "
                f"progress {o['progress']}{mark}")
        return "\n".join(lines)


class RedPlanner:
    def __init__(self, client: LLMClient, memory: RedMemory | None = None, max_retries: int = 1):
        self.client = client
        self.memory = memory or RedMemory()
        self.max_retries = max_retries
        self.schema = plan_json_schema()
        self.stats: Counter[str] = Counter()
        self.latencies: list[float] = []

    def build_prompt(self, round_ctx: dict[str, Any], errors: list[str] | None = None) -> str:
        head = PROMPT_HEAD.format(goals=list(GOALS), scans=list(SCANS))
        body = f"\nThis is round {round_ctx.get('round', 1)}.\nEarlier rounds:\n{self.memory.render()}\n"
        if errors:
            body += "\nPREVIOUS ANSWER HAD PROBLEMS: " + "; ".join(errors) + ". Answer again with a corrected JSON object.\n"
        return head + body

    def plan(self, round_ctx: dict[str, Any]) -> dict[str, Any]:
        """Contract RedAgent.plan(round_ctx) -> dict. Never raises: returns source 'fallback' and plan None on failure."""
        errors: list[str] = []
        calls, tokens_out, latency = 0, 0, 0.0
        for attempt in range(1 + self.max_retries):
            prompt = self.build_prompt(round_ctx, errors or None)
            start = time.perf_counter()
            try:
                text, meta = self.client.generate(prompt, self.schema)
            except Exception as exc:  # noqa: BLE001  network / server problems must not stop an experiment
                self.stats["client_errors"] += 1
                errors = [f"LLM call failed: {type(exc).__name__}"]
                log.warning("LLM call failed: %s", exc)
                break
            calls += 1
            latency += meta.get("latency_s") or (time.perf_counter() - start)
            tokens_out += meta.get("tokens_out") or 0
            plan, errors = parse_plan(text)
            self.stats["plans_requested"] += 1
            if plan is not None:
                self.stats["plans_valid"] += 1
                source = "llm" if attempt == 0 else "llm_retry"
                self.stats["first_try_valid" if attempt == 0 else "retry_valid"] += 1
                return self._result(plan, source, [], calls, tokens_out, latency)
            self.stats["plans_invalid"] += 1
            log.info("invalid Red plan (%s): %s", attempt, errors)
        self.stats["fallbacks"] += 1
        return self._result(None, "fallback", errors, calls, tokens_out, latency)

    def _result(self, plan: RedPlan | None, source: str, errors: list[str], calls: int, tokens_out: int,
                latency: float) -> dict[str, Any]:
        self.latencies.append(latency)
        return {"plan": plan.to_dict() if plan else None, "source": source, "errors": errors,
                "llm_calls": calls, "tokens_out": tokens_out, "llm_latency_s": round(latency, 2)}

    def update(self, trajectories: dict[str, Any] | list[dict[str, Any]]) -> None:
        """Contract RedAgent.update: store round result(s) in memory. Rounds that fell back have no plan to learn from."""
        for entry in [trajectories] if isinstance(trajectories, dict) else trajectories:
            if entry.get("plan"):
                self.memory.add(entry)


class PlannedRed(FiniteStateRedAgent):
    """Executor: plays the current round plan. CybORG builds one per Red agent (more than once), so the plan and the
    counters live on the class; set the plan BEFORE env.reset() / building the environment."""

    _plan: RedPlan | None = None
    _version = 0
    stats: dict[str, Any] = {}

    @classmethod
    def set_plan(cls, plan: RedPlan | None) -> None:
        cls._plan = plan
        cls._version += 1

    @classmethod
    def reset_stats(cls) -> None:
        cls.stats = {"attempts": Counter(), "wins": Counter(), "forced_sleep": 0, "steps": 0}

    def __init__(self, name=None, np_random=None, agent_subnets=None):
        super().__init__(name=name, np_random=np_random, agent_subnets=agent_subnets)
        self._default = (self.state_transitions_probability, self.host_states_priority_list)
        self._applied = -1
        if not PlannedRed.stats:
            PlannedRed.reset_stats()

    def _apply_plan(self) -> None:
        plan = PlannedRed._plan
        if plan is None:  # fallback round: CAGE-4's own scripted behaviour
            self.state_transitions_probability, self.host_states_priority_list = self._default
            self.prioritise_servers = False
        else:
            self.state_transitions_probability, self.host_states_priority_list = compile_plan(plan)
            self.prioritise_servers = plan.prioritise_servers
        self._applied = PlannedRed._version

    def get_action(self, observation, action_space):
        if self._applied != PlannedRed._version:
            self._apply_plan()
        st = PlannedRed.stats
        last, success = observation.get("action"), observation.get("success")
        if last is not None and success is not None and getattr(success, "name", "") != "IN_PROGRESS":
            name = type(last).__name__
            st["attempts"][name] += 1
            st["wins"][name] += getattr(success, "name", "") == "TRUE"
        action = super().get_action(observation, action_space)
        st["steps"] += 1
        ok, reason = is_legal(action, action_space)
        if not ok:  # the FSM picks from the action space, so this should not happen; never play an illegal action
            st["forced_sleep"] += 1
            log.warning("%s: illegal action replaced by Sleep (%s)", self.name, reason)
            return Sleep()
        return action


def outcome_from_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Round result in terms Red can observe. progress = Impact successes (Red's objective is to deny service)."""
    att, win = stats["attempts"], stats["wins"]
    return {
        "exploit_tries": att["ExploitRemoteService"], "exploit_ok": win["ExploitRemoteService"],
        "privesc_ok": win["PrivilegeEscalate"], "impact_ok": win["Impact"], "degrade_ok": win["DegradeServices"],
        "discoveries": att["DiscoverRemoteSystems"] + att["AggressiveServiceDiscovery"] + att["StealthServiceDiscovery"],
        "progress": win["Impact"],
    }
