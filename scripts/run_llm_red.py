"""Run the LLM Red agent (T20) for several rounds: plan once per round, play a full 500-step episode, learn from it.

Needs CAGE-4 cloned to external/cage-challenge-4 and its environment active (docs/setup.md). Examples:
  python scripts/run_llm_red.py --mock --rounds 10 --out results/summaries/red_llm_mock.json
  python scripts/run_llm_red.py --llama-server http://127.0.0.1:8080 --model qwen3-4b --rounds 10 \
      --out results/summaries/red_llm_qwen3-4b.json

Blue is passive (SleepAgent), so this only shows that the planner, validator, fallback and memory work end to end and how
often the LLM's plan is unusable. It says nothing yet about how good the plans are against an acting Blue (T28).
Rounds use tuning seeds 0-9 only. Per-round records go to a JSONL file (--log), the round memory to --memory.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from statistics import mean

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if not CAGE4.exists():
    raise SystemExit("CAGE-4 not found: clone it to external/cage-challenge-4 (see docs/setup.md)")
sys.path.insert(0, str(CAGE4))
sys.path.insert(0, str(ROOT))

from CybORG import CybORG  # noqa: E402
from CybORG.Agents import EnterpriseGreenAgent, SleepAgent  # noqa: E402
from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator  # noqa: E402

from src.agents.blue.llm_client import LlamaServerClient  # noqa: E402
from src.agents.red.llm_red import PlannedRed, RedMemory, RedPlanner, outcome_from_stats  # noqa: E402
from src.agents.red.mock_llm import MockRedLLM  # noqa: E402
from src.agents.red.plan import RedPlan, validate_plan  # noqa: E402

TUNING_SEEDS = range(0, 10)


def play_episode(seed: int, steps: int) -> dict:
    """One full episode with the executor and the plan currently set on PlannedRed; returns Red-observable outcome."""
    PlannedRed.reset_stats()
    sg = EnterpriseScenarioGenerator(blue_agent_class=SleepAgent, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=PlannedRed, steps=steps)
    env = CybORG(sg, "sim", seed=seed)
    env.reset()
    t0 = time.time()
    for _ in range(steps):
        env.step()
        if env.environment_controller.determine_done():
            break
    out = outcome_from_stats(PlannedRed.stats)
    out.update(steps=PlannedRed.stats["steps"], forced_sleep=PlannedRed.stats["forced_sleep"],
               episode_seconds=round(time.time() - t0, 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true", help="use the fault-injecting mock LLM (no GPU)")
    g.add_argument("--llama-server", metavar="URL", help="llama-server base URL, e.g. http://127.0.0.1:8080")
    ap.add_argument("--model", default="local", help="model name to record")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4], help="tuning seeds, cycled over rounds")
    ap.add_argument("--temperature", type=float, default=0.7, help="LLM temperature (plans should vary between rounds)")
    ap.add_argument("--llm-seed", type=int, default=0)
    ap.add_argument("--memory", default=None, help="JSONL memory file (default: next to --log)")
    ap.add_argument("--log", default=None, help="per-round JSONL log")
    ap.add_argument("--out", default=None, help="summary JSON")
    args = ap.parse_args()
    bad = [s for s in args.seeds if s not in TUNING_SEEDS]
    if bad:
        raise SystemExit(f"seeds {bad} are not tuning seeds (0-9); test seeds 100-109 must not be used here")

    if args.mock:
        client, label = MockRedLLM(seed=args.llm_seed), "mock"
    else:
        client = LlamaServerClient(args.llama_server, model=args.model, temperature=args.temperature,
                                   seed=args.llm_seed, max_tokens=400)
        label = args.model
    log_path = pathlib.Path(args.log) if args.log else ROOT / "results" / "red_llm" / f"{label}_rounds.jsonl"
    mem_path = pathlib.Path(args.memory) if args.memory else log_path.with_name(f"{label}_memory.jsonl")
    for p in (log_path, mem_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")
    mem_path.write_text("", encoding="utf-8")  # each run starts with an empty memory

    planner = RedPlanner(client, RedMemory(mem_path))
    rounds = []
    for r in range(1, args.rounds + 1):
        seed = args.seeds[(r - 1) % len(args.seeds)]
        decision = planner.plan({"round": r})
        plan = None
        if decision["plan"] is not None:
            plan = RedPlan(**decision["plan"])
            assert validate_plan(decision["plan"])[0] is not None
        PlannedRed.set_plan(plan)  # None = scripted CAGE-4 default for this round
        outcome = play_episode(seed, args.steps)
        rec = {"round": r, "seed": seed, "source": decision["source"], "plan": decision["plan"],
               "errors": decision["errors"], "llm_calls": decision["llm_calls"], "tokens_out": decision["tokens_out"],
               "llm_latency_s": decision["llm_latency_s"], "outcome": outcome}
        planner.update(rec)
        rounds.append(rec)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        p = decision["plan"]
        print(f"round {r:2d} seed {seed} {decision['source']:9s} "
              f"{(p['goal'] + '/' + p['scan']) if p else 'scripted default':28s} "
              f"impact_ok {outcome['impact_ok']:4d} exploit {outcome['exploit_ok']}/{outcome['exploit_tries']} "
              f"llm {decision['llm_latency_s']}s forced_sleep {outcome['forced_sleep']}")

    s = planner.stats
    requested = s["plans_requested"]
    summary = {
        "model": label, "rounds": args.rounds, "seeds": args.seeds, "steps": args.steps, "temperature": args.temperature,
        "llm_calls": sum(x["llm_calls"] for x in rounds),
        "plans_requested": requested, "plans_valid": s["plans_valid"], "plans_invalid": s["plans_invalid"],
        "invalid_plan_rate": round(s["plans_invalid"] / requested, 3) if requested else None,
        "first_try_valid": s["first_try_valid"], "valid_after_retry": s["retry_valid"],
        "rounds_fell_back_to_scripted": s["fallbacks"], "client_errors": s["client_errors"],
        "median_llm_seconds_per_round": round(sorted(planner.latencies)[len(planner.latencies) // 2], 2) if planner.latencies else None,
        "mean_tokens_out_per_round": round(mean(x["tokens_out"] for x in rounds), 1),
        "illegal_actions_forced_to_sleep": sum(x["outcome"]["forced_sleep"] for x in rounds),
        "steps_played": sum(x["outcome"]["steps"] for x in rounds),
        "distinct_plans": len({json.dumps({k: v for k, v in x["plan"].items() if k != "rationale"}, sort_keys=True)
                               for x in rounds if x["plan"]}),
        "rounds_detail": [{k: x[k] for k in ("round", "seed", "source", "plan", "errors", "outcome")} for x in rounds],
    }
    print("\n" + json.dumps({k: v for k, v in summary.items() if k != "rounds_detail"}, indent=2))
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
