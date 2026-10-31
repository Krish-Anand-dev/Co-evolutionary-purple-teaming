"""Real CAGE-4 episodes for the experiment runner (T28): the real Red agents + ground-truth labels, inside src/loop/runner.py.

`RealEpisodeRunner` is an `episode_fn` for `run_experiment`. One call plays one full episode:
  * Red: a scripted strategy from src/agents/red/scripted.py (T19) or the LLM planner + executor of T20 (`red="llm"`)
  * Blue: a passive or decoy-deploying stand-in until the real Blue (T27) is plugged in, optionally with a rule set acting as
    the DETECTOR (alerts only; the stand-in Blue does not react to them)
  * the telemetry bridge (T16) turns Blue's native observations into events and the T21 labeler marks each one red / benign
  * one contract-format step record per step (with `tn` added so FPR is computable from the step logs) and an EpisodeResult
    carrying the episode metrics, which `round_extras` turns into real round-level numbers (precision, recall, fpr, ...)
Rules of the road enforced here: the held-out Red strategy is refused on tuning seeds; LLM Red memory is kept per seed and
rounds must arrive in order; episodes are serialised with a lock because the labeler patches CybORG for the whole process and
the T20 executor keeps class-level state (use one process per seed set if you want parallelism).
"""
from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from CybORG import CybORG
from CybORG.Agents import EnterpriseGreenAgent, SleepAgent
from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator

from src.agents.baselines.decoy_blue import DecoyBlue
from src.agents.blue.llm_client import LLMClient
from src.agents.red.llm_red import PlannedRed, RedMemory, RedPlanner, outcome_from_stats
from src.agents.red.plan import RedPlan
from src.agents.red.scripted import ALL as RED_STRATEGIES
from src.agents.red.scripted import HELD_OUT
from src.bridge import GroundTruthLabeler, TelemetryBridge
from src.eval.metrics import EpisodeMetrics, evaluate_episode, red_success, round_metrics
from src.loop.config import ExperimentConfig
from src.loop.runner import EpisodeResult
from src.rules.executor import RuleExecutor
from src.rules.loader import load_rules

log = logging.getLogger(__name__)

BLUES = {"passive": SleepAgent, "decoy": DecoyBlue}
LLM_RED = "llm"
# CybORG's own bookkeeping, not decisions of a Red agent: left out of the logged Red actions
_NOT_A_RED_DECISION = {"Sleep", "RedSessionCheck"}
_RUN_LOCK = threading.Lock()


@dataclass(frozen=True)
class RealEpisodeSettings:
    red: str = "cage4_default"          # a key of src/agents/red/scripted.ALL, or "llm"
    blue: str = "passive"               # passive | decoy
    rules_path: str | None = None       # JSON rule set used as the detector; None = no rules (every metric then reads "no alerts")
    memory_dir: str | None = None       # directory for the per-seed Red memory files (red="llm"); None = in memory only


@dataclass
class RealEpisodeResult(EpisodeResult):
    metrics: EpisodeMetrics | None = None
    red_success: int = 0
    rules_emitted: int = 0
    rules_valid: int = 0
    n_events: int = 0
    plan: dict[str, Any] | None = None
    plan_source: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def llm_sampling_seed(base_seed: int, seed: int, round_number: int) -> int:
    """Sampling seed for the LLM call of one (seed, round); deterministic, different for every pair."""
    digest = hashlib.sha256(f"llm|{base_seed}|{seed}|{round_number}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2**31 - 1)


def derive_env_seed(seed: int, round_number: int, episode_number: int) -> int:
    """CybORG seed for one episode. Round 1 / episode 0 uses the configured seed itself (so it matches every earlier
    measurement with that seed); every other episode gets a hash-derived seed, so episodes differ but cannot collide with a
    different configured seed (tuning 0-9 vs test 100-109)."""
    if round_number == 1 and episode_number == 0:
        return seed
    digest = hashlib.sha256(f"{seed}|{round_number}|{episode_number}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2**31 - 1) + 1000


class RealEpisodeRunner:
    """Callable episode_fn(config, seed, round_number, episode_number, run_id) -> RealEpisodeResult."""

    def __init__(self, settings: RealEpisodeSettings, llm_client: LLMClient | None = None):
        if settings.blue not in BLUES:
            raise ValueError(f"blue must be one of {sorted(BLUES)}")
        if settings.red != LLM_RED and settings.red not in RED_STRATEGIES:
            raise ValueError(f"red must be 'llm' or one of {sorted(RED_STRATEGIES)}")
        if settings.red == LLM_RED and llm_client is None:
            raise ValueError("red='llm' needs an llm_client")
        self.settings, self.llm_client = settings, llm_client
        self.rules = load_rules(settings.rules_path) if settings.rules_path else []
        self.executor = RuleExecutor(self.rules)
        if self.executor.rejected:
            raise ValueError(f"rules rejected by the validator: {self.executor.rejected}")
        self._labeler = GroundTruthLabeler()
        self._planners: dict[int, RedPlanner] = {}
        self._round_state: dict[int, dict[str, Any]] = {}

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        """Undo the CybORG patches (the labeler installs them for the whole process)."""
        self._labeler.uninstall()

    def __call__(self, config: ExperimentConfig, seed: int, round_number: int, episode_number: int, run_id: str) -> RealEpisodeResult:
        if self.settings.red in HELD_OUT and seed in config.tuning_seeds:
            raise ValueError(f"red strategy {self.settings.red!r} is held out: it may only be used on test seeds, never on "
                             f"tuning seed {seed} (see docs/red-strategies.md)")
        with _RUN_LOCK:
            return self._play(config, seed, round_number, episode_number, run_id)

    # ------------------------------------------------------------------ Red selection
    def _planner(self, seed: int) -> RedPlanner:
        if seed not in self._planners:
            path = None
            if self.settings.memory_dir:
                path = Path(self.settings.memory_dir) / f"red_memory_seed{seed}.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")  # every run starts with an empty memory
            self._planners[seed] = RedPlanner(self.llm_client, RedMemory(path))
        return self._planners[seed]

    def _prepare_red(self, seed: int, round_number: int, episode_number: int, base_seed: int = 0) -> tuple[type, dict[str, Any]]:
        """Class CybORG will instantiate for every Red agent, plus what the LLM planner did this round."""
        if self.settings.red != LLM_RED:
            return RED_STRATEGIES[self.settings.red], {"plan": None, "source": None, "llm_calls": 0, "llm_latency_s": 0.0}
        planner = self._planner(seed)
        state = self._round_state.get(seed)
        if state is None or state["round"] != round_number:
            expected = 1 if state is None else state["round"] + 1
            if round_number != expected:
                raise RuntimeError(f"LLM Red needs the rounds of seed {seed} in order (got round {round_number}, expected "
                                   f"{expected}): run with one worker")
            if state is not None:  # close the previous round: its pooled outcome goes into the memory
                planner.update({"round": state["round"], "plan": state["decision"]["plan"], "outcome": _pool(state["outcomes"])})
            # Each (seed, round) samples the LLM with its own seed: seeds are independent replicates, and one shared sampling seed
            # made all of them draw the same plan in the same round (seen in the first T28 LLM run).
            if hasattr(self.llm_client, "seed"):
                self.llm_client.seed = llm_sampling_seed(base_seed, seed, round_number)
            decision = planner.plan({"round": round_number})
            state = {"round": round_number, "decision": decision, "outcomes": []}
            self._round_state[seed] = state
            fresh = True
        else:
            decision, fresh = state["decision"], False
        PlannedRed.set_plan(RedPlan(**decision["plan"]) if decision["plan"] else None)  # None = scripted default this round
        info = {"plan": decision["plan"], "source": decision["source"],
                "llm_calls": decision["llm_calls"] if fresh else 0, "llm_latency_s": decision["llm_latency_s"] if fresh else 0.0}
        return PlannedRed, info

    # ------------------------------------------------------------------ one episode
    def _play(self, config: ExperimentConfig, seed: int, round_number: int, episode_number: int, run_id: str) -> RealEpisodeResult:
        labeler = self._labeler.install()
        red_cls, red_info = self._prepare_red(seed, round_number, episode_number, base_seed=config.seed)
        if self.settings.red == LLM_RED:
            PlannedRed.reset_stats()
        env_seed = derive_env_seed(seed, round_number, episode_number)
        sg = EnterpriseScenarioGenerator(blue_agent_class=BLUES[self.settings.blue], green_agent_class=EnterpriseGreenAgent,
                                         red_agent_class=red_cls, steps=config.steps)
        env = CybORG(sg, "sim", seed=env_seed)
        env.reset()
        labeler.reset()  # drop anything recorded while the environment was being built
        bridge = TelemetryBridge(env_seed, labeler=labeler)
        blue_agents = [a for a in env.agents if a.startswith("blue")]
        active_rules = sorted(r.rule_id for r in self.executor.rules)

        records: list[dict[str, Any]] = []
        episode_events: list[dict[str, Any]] = []
        episode_alerts: list[str] = []
        total_reward, log_pos, last_step = 0.0, 0, 0
        for step in range(config.steps):
            env.step()
            obs = {}
            for a in blue_agents:
                body = {k: v for k, v in env.get_observation(a).items() if k not in ("success", "action")}
                if body:
                    obs[a] = body
            events = bridge.step_events(step, obs)
            if any(e.label_red is None for e in events):
                raise RuntimeError(f"unlabelled event at seed {seed} step {step}: the labeler is not attached correctly")
            alerts = self.executor.run(e.visible() for e in events)
            alerted = {a.event_id for a in alerts}
            red_ev = [e for e in events if e.label_red == 1]
            tp = sum(e.event_id in alerted for e in red_ev)
            fp = sum(e.event_id in alerted for e in events if e.label_red == 0)
            fn, tn = len(red_ev) - tp, len(events) - len(red_ev) - fp
            episode_events += [{"event_id": e.event_id, "step": e.step, "label_red": e.label_red} for e in events]
            episode_alerts += sorted(alerted)

            new_actions = labeler.action_log[log_pos:]
            log_pos = len(labeler.action_log)
            red_actions = {r["agent"]: r["action"] for r in new_actions if r["action"] not in _NOT_A_RED_DECISION}
            reward = env.get_rewards()["Blue"]
            penalty = float(reward.get("BlueRewardMachine", 0))
            cost = float(reward.get("action_cost", 0))
            total_reward += penalty + cost
            last_step = step
            records.append({
                "run_id": run_id, "condition": config.condition, "seed": seed, "round": round_number, "phase": "eval",
                "episode": episode_number, "step": step, "agent": "env", "action": red_actions,
                "reward_components": {"blue_penalty": penalty, "blue_action_cost": cost},
                "alerts": [{"rule_id": a.rule_id, "event_id": a.event_id} for a in alerts],
                "active_rules": active_rules, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "events": len(events), "llm_calls": red_info["llm_calls"] if step == 0 else 0,
                "llm_latency_s": red_info["llm_latency_s"] if step == 0 else 0.0})
            if env.environment_controller.determine_done():
                break

        metrics = evaluate_episode(episode_events, episode_alerts, last_step=last_step)
        success = red_success(labeler.action_log)
        if self.settings.red == LLM_RED:
            self._round_state[seed]["outcomes"].append(outcome_from_stats(PlannedRed.stats))
        return RealEpisodeResult(
            seed=seed, round_number=round_number, episode_number=episode_number, step_records=records, reward=total_reward,
            metrics=metrics, red_success=success, rules_emitted=len(self.rules), rules_valid=len(self.executor.rules),
            n_events=len(episode_events), plan=red_info["plan"], plan_source=red_info["source"],
            extras={"env_seed": env_seed,
                    "red_actions": len([r for r in labeler.action_log if r["action"] not in _NOT_A_RED_DECISION])})


def _pool(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the per-episode Red outcomes of one round for the Red memory (progress = successful Impacts)."""
    keys = ("exploit_tries", "exploit_ok", "privesc_ok", "impact_ok", "degrade_ok", "discoveries", "progress")
    return {k: sum(o[k] for o in outcomes) for k in keys}


def round_extras(results: list[EpisodeResult]) -> dict[str, Any]:
    """Round-level fields for `run_experiment(round_extras_fn=...)`: pooled precision / recall / fpr, mean time to detect, ..."""
    eps = [r for r in results if isinstance(r, RealEpisodeResult) and r.metrics is not None]
    if not eps:
        return {}
    rm = round_metrics([r.metrics for r in eps])
    emitted = eps[0].rules_emitted
    return {
        "rules_emitted": emitted, "rules_valid": eps[0].rules_valid,
        "rule_validity": (eps[0].rules_valid / emitted) if emitted else None,
        "precision": rm["precision"], "recall": rm["recall"], "fpr": rm["fpr"],
        "red_success": sum(r.red_success for r in eps) / len(eps), "time_to_detect": rm["time_to_detect"],
        "detection_rate": rm["detection_rate"], "events": sum(r.n_events for r in eps),
        "tp": rm["tp"], "fp": rm["fp"], "fn": rm["fn"], "tn": rm["tn"],
        "red_plan": eps[0].plan, "red_plan_source": eps[0].plan_source,
        "mean_reward": sum(r.reward for r in eps) / len(eps),
    }
