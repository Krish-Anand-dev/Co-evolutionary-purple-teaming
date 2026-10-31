"""'Hello agents' (T07): one full CAGE-4 episode with OUR random Blue and OUR random Red.

Needs CAGE-4 cloned to external/cage-challenge-4 and its environment active (docs/setup.md). Example:
  python scripts/hello_agents.py --seed 0 --out results/summaries/hello_agents_seed0.json

Red: every Red agent CybORG creates is a RandomRed (src/agents/baselines/random_red.py).
Blue: five RandomBlue agents choose action indices through CybORG's EnterpriseMAE wrapper.
Green stays the default EnterpriseGreenAgent. Checks reported at the end:
  * Red: how many actions the agent itself rejected as illegal, and how many CybORG recorded as InvalidAction
  * Blue: how many chosen indices were outside the action mask
  * the episode ran the full number of steps
Nothing here modifies CybORG.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time
from collections import Counter
from statistics import mean

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if not CAGE4.exists():
    raise SystemExit("CAGE-4 not found: clone it to external/cage-challenge-4 (see docs/setup.md)")
sys.path.insert(0, str(CAGE4))
sys.path.insert(0, str(ROOT))

from CybORG import CybORG  # noqa: E402
from CybORG.Agents import EnterpriseGreenAgent, SleepAgent  # noqa: E402
from CybORG.Agents.Wrappers.EnterpriseMAE import EnterpriseMAE  # noqa: E402
from CybORG.Simulator.Actions import InvalidAction  # noqa: E402
from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator  # noqa: E402

from src.agents.baselines.random_blue import RandomBlue  # noqa: E402
from src.agents.baselines.random_red import RandomRed  # noqa: E402

log = logging.getLogger("hello_agents")

RED_AGENTS: list[RandomRed] = []


class RegisteredRandomRed(RandomRed):
    """RandomRed that records itself so the script can read its counters after the episode."""

    def __init__(self, name, np_random=None):
        super().__init__(name, np_random=np_random)
        RED_AGENTS.append(self)


def run_episode(seed: int, steps: int) -> dict:
    RED_AGENTS.clear()
    sg = EnterpriseScenarioGenerator(blue_agent_class=SleepAgent, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=RegisteredRandomRed, steps=steps)
    cyborg = CybORG(sg, "sim", seed=seed)
    env = EnterpriseMAE(cyborg)
    _, info = env.reset()

    blues = {a: RandomBlue(a, seed=seed * 1000 + i) for i, a in enumerate(sorted(env.agents))}
    red_names = [a for a in cyborg.environment_controller.agent_interfaces if a.startswith("red")]
    rewards: list[float] = []
    invalid_red = 0
    out_of_mask = 0
    blue_actions = Counter()
    start = time.time()
    done_steps = 0
    env_signalled_done = False
    for step in range(steps):
        actions = {}
        for agent in env.agents:
            mask = info.get(agent, {}).get("action_mask")
            idx = blues[agent].act(env.action_space(agent).n, mask)
            if mask is not None and not mask[idx]:
                out_of_mask += 1
            actions[agent] = idx
            blue_actions[idx] += 1
        _, rew, term, trunc, info = env.step(actions)
        rewards.append(mean(rew.values()) if rew else 0.0)
        for r in red_names:
            if isinstance(cyborg.get_last_action(r), InvalidAction):
                invalid_red += 1
        done_steps = step + 1
        if trunc.get("__all__"):
            env_signalled_done = True
            break

    # CybORG builds the Red agent objects more than once (scenario generation); only those that acted played.
    played = [r for r in RED_AGENTS if r.steps > 0]
    red_counts = Counter()
    for r in played:
        red_counts.update(r.action_counts)
    return {
        "seed": seed,
        "steps_requested": steps,
        "steps_run": done_steps,
        # CybORG ends an episode of `steps` at step_count >= steps-1 (EnterpriseScenarioGenerator.determine_done),
        # so a 500-step episode is 499 env steps; the official evaluation.py behaves the same.
        "steps_expected_by_cyborg": steps - 1,
        "env_signalled_done": env_signalled_done,
        "full_episode": env_signalled_done and done_steps == steps - 1,
        "total_reward_mean_over_agents": sum(rewards),
        "seconds": round(time.time() - start, 1),
        "red": {
            "agents_that_acted": len(played),
            "agent_instances_created": len(RED_AGENTS),
            "actions_by_type": dict(sorted(red_counts.items())),
            "illegal_rejected_by_agent": sum(r.illegal_count for r in RED_AGENTS),
            "invalid_action_recorded_by_env": invalid_red,
        },
        "blue": {
            "agents": sorted(blues),
            "distinct_action_indices_used": len(blue_actions),
            "chosen_outside_action_mask": out_of_mask,
            "fallbacks_when_mask_empty": sum(b.illegal_count for b in blues.values()),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--out", default=None, help="write the summary as JSON")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    summary = run_episode(args.seed, args.steps)
    print(json.dumps(summary, indent=2))
    ok = (summary["full_episode"] and summary["red"]["illegal_rejected_by_agent"] == 0
          and summary["red"]["invalid_action_recorded_by_env"] == 0
          and summary["blue"]["chosen_outside_action_mask"] == 0)
    print("legal-action checks:", "OK" if ok else "FAILED")
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print("wrote", out)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
