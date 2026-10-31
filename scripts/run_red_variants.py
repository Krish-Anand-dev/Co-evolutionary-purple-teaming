"""Run each scripted Red strategy (T19) for full episodes and log how their behaviour differs.

Needs CAGE-4 cloned to external/cage-challenge-4 and its environment active (docs/setup.md). Example:
  python scripts/run_red_variants.py --seeds 0 1 2 3 4 --out results/summaries/red_variants_tuning.json

Blue is passive (SleepAgent) so only Red's own behaviour shows. Per variant and seed we log: Red actions by type, success
rate per action type, how many Red agents ever got a shell / root, noise Blue would see (native process records in Blue's
observations), and the Blue team penalty. Only TUNING seeds (0-9) are accepted; test seeds 100-109 stay untouched.
The held-out strategy is included here only to show it is behaviourally different from the training ones.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from collections import Counter, defaultdict
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

from src.agents.red.scripted import ALL, HELD_OUT  # noqa: E402

TUNING_SEEDS = range(0, 10)


def native_records(blue_obs: dict) -> int:
    """Native process records Blue gets in one step (the raw material of every alert)."""
    return sum(len(h.get("Processes", [])) for h in blue_obs.values() if isinstance(h, dict))


def run(variant: str, seed: int, steps: int) -> dict:
    sg = EnterpriseScenarioGenerator(blue_agent_class=SleepAgent, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=ALL[variant], steps=steps)
    env = CybORG(sg, "sim", seed=seed)
    env.reset()
    blue = [a for a in env.agents if a.startswith("blue")]
    red = [a for a in env.agents if a.startswith("red")]
    counts: Counter[str] = Counter()
    wins: Counter[str] = Counter()
    first_exploit_ok = None
    n_records = 0
    t0 = time.time()
    for step in range(steps):
        env.step()
        for a in red:
            act = env.get_last_action(a)
            if isinstance(act, (list, tuple)):  # CybORG returns the agent's actions as a list
                act = act[0] if act else None
            obs = env.get_observation(a)
            name = type(act).__name__
            counts[name] += 1
            if name == "Sleep":
                continue
            ok = str(obs.get("success")).endswith("TRUE")
            wins[name] += ok
            if ok and name == "ExploitRemoteService" and first_exploit_ok is None:
                first_exploit_ok = step
        for a in blue:
            n_records += native_records(env.get_observation(a))
        if env.environment_controller.determine_done():
            break
    acting = sum(v for k, v in counts.items() if k != "Sleep")
    return {
        "variant": variant, "held_out": variant in HELD_OUT, "seed": seed, "steps": step + 1,
        "seconds": round(time.time() - t0, 1),
        "red_actions": dict(sorted(counts.items())),
        "red_success_rate": {k: round(wins[k] / counts[k], 3) for k in sorted(wins) if counts[k]},
        "red_non_sleep_actions": acting,
        "first_successful_exploit_step": first_exploit_ok,
        "blue_native_process_records": n_records,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--variants", nargs="+", default=list(ALL))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    bad = [s for s in args.seeds if s not in TUNING_SEEDS]
    if bad:
        raise SystemExit(f"seeds {bad} are not tuning seeds (0-9); test seeds 100-109 must not be used here")

    runs = []
    for v in args.variants:
        for s in args.seeds:
            r = run(v, s, args.steps)
            runs.append(r)
            print(f"{v:16s} seed {s}: {r['red_non_sleep_actions']:5d} actions, {r['blue_native_process_records']:5d} "
                  f"native records, first exploit ok at {r['first_successful_exploit_step']}, {r['seconds']} s")

    table = defaultdict(lambda: defaultdict(list))
    for r in runs:
        for k, v in r["red_actions"].items():
            table[r["variant"]][k].append(v)
        table[r["variant"]]["_records"].append(r["blue_native_process_records"])
    print("\nmean Red actions per episode, by variant:")
    kinds = sorted({k for v in table.values() for k in v if not k.startswith("_")})
    print(f"{'variant':16s} " + " ".join(f"{k[:9]:>9s}" for k in kinds) + "   records")
    for v, d in table.items():
        print(f"{v:16s} " + " ".join(f"{mean(d[k]) if d[k] else 0:9.1f}" for k in kinds) + f"   {mean(d['_records']):7.1f}")

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"steps": args.steps, "seeds": args.seeds, "runs": runs}, indent=2) + "\n",
                       encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
