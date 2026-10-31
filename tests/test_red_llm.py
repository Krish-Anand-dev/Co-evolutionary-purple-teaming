"""T20 LLM Red agent: plan validation and compilation, planner retry / fallback, memory, and the executor in a live episode."""
from __future__ import annotations

import itertools
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if CAGE4.exists():
    sys.path.insert(0, str(CAGE4))

pytest.importorskip("CybORG")
pytest.importorskip("ray")

from src.agents.red.llm_red import PlannedRed, RedMemory, RedPlanner  # noqa: E402
from src.agents.red.mock_llm import MockRedLLM  # noqa: E402
from src.agents.red.plan import SCANS, RedPlan, compile_plan, parse_plan, validate_plan  # noqa: E402

GOOD = {"goal": "balanced", "scan": "mixed", "probe_decoys": 0.4, "prioritise_servers": True,
        "impact_bias": 0.5, "degrade_share": 0.3, "rationale": "Mix it up."}


def good(**over):
    return {**GOOD, **over}


# ---------- validator ----------
def test_valid_plan_parses_even_with_fence_and_prose():
    plan, errs = parse_plan("Sure!\n```json\n" + json.dumps(GOOD) + "\n```")
    assert errs == [] and plan.scan == "mixed" and plan.impact_bias == 0.5


@pytest.mark.parametrize("bad", [
    good(goal="destroy_all"), good(scan="loud"), good(impact_bias=1.2), good(probe_decoys=-0.1),
    good(degrade_share="high"), good(prioritise_servers="yes"), good(impact_bias=True),
    good(rationale="x" * 301), good(extra=1),
])
def test_invalid_plans_are_rejected(bad):
    plan, errs = validate_plan(bad)
    assert plan is None and errs


def test_missing_field_and_non_json_are_rejected():
    obj = dict(GOOD)
    del obj["goal"]
    assert validate_plan(obj)[0] is None
    assert parse_plan("I will attack the servers.")[0] is None
    assert parse_plan("[1, 2]")[0] is None


# ---------- compiler ----------
@pytest.mark.parametrize("scan,probe,ib,ds", list(itertools.product(SCANS, (0.0, 0.5, 1.0), (0.0, 0.5, 1.0), (0.0, 1.0))))
def test_every_compiled_row_is_a_probability_distribution(scan, probe, ib, ds):
    plan = RedPlan("balanced", scan, probe, True, ib, ds)
    table, priority = compile_plan(plan)
    assert set(table) == {"K", "KD", "S", "SD", "U", "UD", "R", "RD"}
    for state, row in table.items():
        assert len(row) == 9 and row[8] is None, state  # Withdraw never offered
        assert abs(sum(v for v in row if v is not None) - 1.0) < 1e-9, (state, row)
    assert abs(sum(priority.values()) - 100) < 1e-6


def test_scan_field_changes_which_scan_is_offered():
    agg, _ = compile_plan(RedPlan("fast_impact", "aggressive", 0.2, False, 0.8, 0.2))
    ste, _ = compile_plan(RedPlan("stealth_recon", "stealthy", 0.2, False, 0.2, 0.2))
    assert agg["K"][2] is None and agg["K"][1] is not None
    assert ste["K"][1] is None and ste["K"][2] is not None


# ---------- planner ----------
class Scripted:
    """Returns the given answers in order; an Exception instance is raised instead."""
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), 0

    def generate(self, prompt, schema=None):
        self.calls += 1
        a = self.answers[min(self.calls - 1, len(self.answers) - 1)]
        if isinstance(a, Exception):
            raise a
        return a, {"model": "scripted", "latency_s": 0.1, "tokens_out": 10}


def test_planner_valid_first_try():
    p = RedPlanner(Scripted(json.dumps(GOOD)))
    r = p.plan({"round": 1})
    assert r["source"] == "llm" and r["plan"]["scan"] == "mixed" and r["llm_calls"] == 1
    assert p.stats["fallbacks"] == 0


def test_planner_retries_once_with_the_errors_then_succeeds():
    client = Scripted(json.dumps(good(impact_bias=3)), json.dumps(GOOD))
    seen = []
    orig = client.generate
    client.generate = lambda prompt, schema=None: (seen.append(prompt), orig(prompt, schema))[1]
    r = RedPlanner(client).plan({"round": 1})
    assert r["source"] == "llm_retry" and r["llm_calls"] == 2
    assert "PREVIOUS ANSWER HAD PROBLEMS" in seen[1] and "impact_bias" in seen[1]


def test_planner_falls_back_when_answers_stay_invalid():
    p = RedPlanner(Scripted("no json here"))
    r = p.plan({"round": 1})
    assert r["plan"] is None and r["source"] == "fallback" and r["errors"]
    assert p.stats["fallbacks"] == 1 and p.stats["plans_invalid"] == 2


def test_planner_survives_a_dead_server():
    p = RedPlanner(Scripted(ConnectionError("down")))
    r = p.plan({"round": 1})
    assert r["plan"] is None and r["source"] == "fallback"
    assert p.stats["client_errors"] == 1


def test_mock_llm_exercises_every_path_and_never_raises():
    p = RedPlanner(MockRedLLM(seed=3))
    sources = {p.plan({"round": i})["source"] for i in range(60)}
    assert {"llm", "fallback"} <= sources
    assert p.stats["plans_requested"] >= 60


# ---------- memory ----------
def test_memory_persists_renders_and_skips_fallback_rounds(tmp_path):
    path = tmp_path / "mem.jsonl"
    planner = RedPlanner(Scripted(json.dumps(GOOD)), RedMemory(path))
    outcome = {"exploit_tries": 10, "exploit_ok": 4, "privesc_ok": 2, "impact_ok": 7, "degrade_ok": 1,
               "discoveries": 5, "progress": 7}
    planner.update({"round": 1, "plan": GOOD, "outcome": outcome})
    planner.update({"round": 2, "plan": None, "outcome": outcome})  # fallback round: nothing to learn about a plan
    assert len(RedMemory(path).entries) == 1
    text = RedMemory(path).render()
    assert "round 1" in text and "Impact ok 7" in text and "best so far" in text
    assert "round 1" in planner.build_prompt({"round": 2})
    assert RedMemory().render() == "No earlier rounds."


# ---------- executor in a live episode ----------
def _episode(plan, steps=60, seed=2):
    from CybORG import CybORG
    from CybORG.Agents import EnterpriseGreenAgent, SleepAgent
    from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator

    PlannedRed.reset_stats()
    PlannedRed.set_plan(plan)
    sg = EnterpriseScenarioGenerator(blue_agent_class=SleepAgent, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=PlannedRed, steps=steps)
    env = CybORG(sg, "sim", seed=seed)
    env.reset()
    for _ in range(steps - 1):
        env.step()
    return PlannedRed.stats


def test_executor_obeys_scan_choice_and_never_plays_illegal_actions():
    agg = _episode(RedPlan("fast_impact", "aggressive", 0.0, True, 0.9, 0.2))
    assert agg["forced_sleep"] == 0 and agg["steps"] > 100
    assert agg["attempts"]["StealthServiceDiscovery"] == 0 and agg["attempts"]["AggressiveServiceDiscovery"] > 0
    ste = _episode(RedPlan("stealth_recon", "stealthy", 0.0, False, 0.2, 0.2))
    assert ste["forced_sleep"] == 0
    assert ste["attempts"]["AggressiveServiceDiscovery"] == 0 and ste["attempts"]["StealthServiceDiscovery"] > 0


def test_fallback_round_runs_the_scripted_default():
    st = _episode(None)
    assert st["forced_sleep"] == 0 and st["steps"] > 100
    assert st["attempts"]["Withdraw"] == 0
    PlannedRed.set_plan(None)


def test_impact_bias_zero_really_means_no_impact():
    """Regression: after a discovery action a root host is in state RD, which used to offer Impact regardless of the plan."""
    quiet = _episode(RedPlan("stealth_recon", "stealthy", 0.3, False, 0.0, 0.5), steps=150)
    loud = _episode(RedPlan("fast_impact", "aggressive", 0.0, True, 1.0, 0.0), steps=150)
    assert quiet["attempts"]["Impact"] + quiet["attempts"]["DegradeServices"] == 0
    assert loud["attempts"]["Impact"] > 0
    PlannedRed.set_plan(None)
