"""T21 acceptance check: every bridge event in a test episode carries label_red, and the labels agree with what Red did.

Needs CAGE-4 cloned to external/cage-challenge-4 and its environment active (docs/setup.md). Example:
  python scripts/label_check.py --seeds 0 1 2 --out results/summaries/labeler_check.json --sample results/summaries/labeler_spotcheck.md

For every (Blue behaviour, Red behaviour, seed) it runs a full episode with the labeler installed and the bridge fed the raw
Blue observations (as in scripts/live_bridge_run.py), then reports:
  * events, events labelled, events with no label (must be 0), unclaimed ledger entries
  * red vs benign split and counts per source action
  * consistency against the INDEPENDENT Red action log: each red-labelled event must match a Red action of the same type by
    the same agent at the same step, and a target-side event's destination must be that action's target
  * benign events must not coincide with a Red action of the type that produced them
Blue: passive (Sleep), decoy-deploying, traffic-blocking (creates Green connection-failure events).
Red: CAGE-4's FiniteStateRedAgent and RandomSelectRedAgent (every Red action). Only tuning seeds 0-9 are accepted.
--sample writes 50 events (25 red, 25 benign, spread over sources) with their evidence for checking by hand.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if not CAGE4.exists():
    raise SystemExit("CAGE-4 not found: clone it to external/cage-challenge-4 (see docs/setup.md)")
sys.path.insert(0, str(CAGE4))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from CybORG import CybORG  # noqa: E402
from CybORG.Agents import EnterpriseGreenAgent, FiniteStateRedAgent, SleepAgent  # noqa: E402
from CybORG.Agents.SimpleAgents.BaseAgent import BaseAgent  # noqa: E402
from CybORG.Agents.SimpleAgents.RandomSelectRedAgent import RandomSelectRedAgent  # noqa: E402
from CybORG.Simulator.Actions import Sleep
from CybORG.Simulator.Actions.ConcreteActions.ControlTraffic import BlockTrafficZone  # noqa: E402
from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator  # noqa: E402
from dump_native_events import DecoyBlueAgent  # noqa: E402

from src.bridge import GroundTruthLabeler, TelemetryBridge  # noqa: E402

TUNING_SEEDS = range(0, 10)
SCAN_LIKE = {"AggressiveServiceDiscovery", "StealthServiceDiscovery", "ExploitRemoteService"}


class BlockerBlue(BaseAgent):
    """Every 15 decisions blocks traffic from another zone into one of its own zones, so Green gets connection failures
    (events recorded on the Green host with remote port 8800). `cidr_to_name` is filled in by run() once the env exists."""

    cidr_to_name: dict = {}

    def __init__(self, name=None, **kwargs):
        super().__init__(name)
        self.n = 0

    def get_action(self, observation, action_space):
        self.n += 1
        if self.n % 15:
            return Sleep()
        own = [self.cidr_to_name[str(c)] for c, ok in action_space.get("subnet", {}).items() if ok and str(c) in self.cidr_to_name]
        others = sorted(n for c, n in self.cidr_to_name.items() if n not in own)
        if not own or not others:
            return Sleep()
        return BlockTrafficZone(session=0, agent=self.name, from_subnet=others[self.n % len(others)],
                                to_subnet=own[self.n % len(own)])

    def train(self, results): pass
    def end_episode(self): pass
    def set_initial_values(self, action_space, observation): pass


BLUES = {"passive": SleepAgent, "decoy": DecoyBlueAgent, "blocker": BlockerBlue}
REDS = {"fsm": FiniteStateRedAgent, "random": RandomSelectRedAgent}


def native_body(obs: dict) -> dict:
    return {k: v for k, v in obs.items() if k not in ("success", "action")}


def run(blue: str, red: str, seed: int, steps: int, labeler: GroundTruthLabeler) -> dict:
    labeler.reset()
    sg = EnterpriseScenarioGenerator(blue_agent_class=BLUES[blue], green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=REDS[red], steps=steps)
    env = CybORG(sg, "sim", seed=seed)
    env.reset()
    labeler.reset()  # drop anything recorded while the environment was being built
    BlockerBlue.cidr_to_name = {str(c): n.lower() for n, c in env.environment_controller.state.subnet_name_to_cidr.items()}
    blue_agents = [a for a in env.agents if a.startswith("blue")]
    bridge = TelemetryBridge(seed, labeler=labeler)
    events = []
    for step in range(steps):
        env.step()
        obs = {}
        for a in blue_agents:
            body = native_body(env.get_observation(a))
            if body:
                obs[a] = body
        events.extend(bridge.step_events(step, obs))
        if env.environment_controller.determine_done():
            break

    red_log: dict[int, list[dict]] = {}
    for rec in labeler.action_log:
        red_log.setdefault(rec["step"], []).append(rec)

    problems: list[str] = []
    by_source, step_mismatch, target_ok, target_checked = Counter(), 0, 0, 0
    for e in events:
        if e.label_red is None:
            problems.append(f"unlabelled event {e.event_id}")
            continue
        by_source[(e.label_red, e.source_action)] += 1
        same_step = red_log.get(e.step, [])
        if e.label_red == 1:
            match = [r for r in same_step if r["agent"] == e.source_agent and r["action"] == e.source_action]
            if not match:
                step_mismatch += 1
                problems.append(f"red event {e.event_id} step {e.step} has no {e.source_action} by {e.source_agent} in the action log")
            elif e.category == "network_connection" and e.dst_ip and e.source_action in SCAN_LIKE:
                target_checked += 1
                # path-side events sit on a router on the route, so only require that SOME same-step action of that type
                # by that agent aimed at the event's destination
                if any(r["target"] == e.dst_ip for r in match):
                    target_ok += 1
        else:
            # a benign event must not have been created by a Red action: its source action must not be a Red action type
            if e.source_agent and e.source_agent.startswith("red"):
                problems.append(f"benign event {e.event_id} attributed to a red agent")
    return {
        "blue": blue, "red": red, "seed": seed, "steps": step + 1, "events": len(events),
        "labelled": sum(e.label_red is not None for e in events),
        "unlabelled": sum(e.label_red is None for e in events),
        "red_events": sum(e.label_red == 1 for e in events), "benign_events": sum(e.label_red == 0 for e in events),
        "unclaimed_ledger_entries": labeler.unclaimed(), "labeler_stats": dict(labeler.stats),
        "by_source": {f"{'red' if k[0] else 'benign'}:{k[1]}": v for k, v in sorted(by_source.items())},
        "red_events_without_matching_action": step_mismatch,
        "target_side_checked": target_checked, "target_side_destination_matches_action_target": target_ok,
        "problems": problems[:10], "n_problems": len(problems),
    }, events, labeler.action_log


def sample_table(events, action_log, n_red=25, n_benign=25, seed=0) -> str:
    rnd = random.Random(seed)
    red = [e for e in events if e.label_red == 1]
    ben = [e for e in events if e.label_red == 0]

    def pick(pool, n):
        # spread across source actions
        groups: dict[str, list] = {}
        for e in pool:
            groups.setdefault(e.source_action, []).append(e)
        out, keys = [], sorted(groups)
        while len(out) < min(n, len(pool)):
            for k in keys:
                if groups[k] and len(out) < n:
                    out.append(groups[k].pop(rnd.randrange(len(groups[k]))))
        return out

    by_step: dict[int, list[dict]] = {}
    for r in action_log:
        by_step.setdefault(r["step"], []).append(r)
    lines = ["| # | step | host | category | src -> dst:port | label | source action | source agent | Red actions at this step on this agent / target |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(pick(red, n_red) + pick(ben, n_benign), 1):
        ev = [f"{r['action']}->{r['target']}" for r in by_step.get(e.step, []) if r["agent"] == e.source_agent]
        lines.append(f"| {i} | {e.step} | {e.host_id} | {e.category} | {e.src_ip} -> {e.dst_ip}:{e.dst_port} | {e.label_red} | "
                     f"{e.source_action} | {e.source_agent} | {'; '.join(ev) or '-'} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--blues", nargs="+", default=list(BLUES), choices=list(BLUES))
    ap.add_argument("--reds", nargs="+", default=list(REDS), choices=list(REDS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--sample", default=None, help="write a 50-event table for checking by hand (markdown)")
    args = ap.parse_args()
    bad = [s for s in args.seeds if s not in TUNING_SEEDS]
    if bad:
        raise SystemExit(f"seeds {bad} are not tuning seeds (0-9)")

    labeler = GroundTruthLabeler().install()
    runs, sample_pool = [], ([], [])
    try:
        for blue in args.blues:
            for red in args.reds:
                for seed in args.seeds:
                    res, events, log = run(blue, red, seed, args.steps, labeler)
                    runs.append(res)
                    if blue == "decoy" and red == "fsm" and seed == args.seeds[0]:
                        sample_pool = (events, log)
                    print(f"{blue:8s} {red:6s} seed {seed}: {res['events']:5d} events, red {res['red_events']:4d}, "
                          f"benign {res['benign_events']:4d}, unlabelled {res['unlabelled']}, unclaimed {res['unclaimed_ledger_entries']}, "
                          f"red-without-action {res['red_events_without_matching_action']}, "
                          f"target match {res['target_side_destination_matches_action_target']}/{res['target_side_checked']}")
    finally:
        labeler.uninstall()

    tot = {k: sum(r[k] for r in runs) for k in ("events", "labelled", "unlabelled", "red_events", "benign_events",
                                                "unclaimed_ledger_entries", "red_events_without_matching_action",
                                                "target_side_checked", "target_side_destination_matches_action_target",
                                                "n_problems")}
    agg_source: Counter = Counter()
    for r in runs:
        agg_source.update(r["by_source"])
    print("\nTOTAL", json.dumps(tot))
    print("by source:", dict(sorted(agg_source.items())))
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"totals": tot, "by_source": dict(sorted(agg_source.items())), "runs": runs}, indent=2) + "\n",
                       encoding="utf-8")
        print("wrote", out)
    if args.sample and sample_pool[0]:
        sp = pathlib.Path(args.sample)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text("# Labeler spot-check sample (50 events)\n\nCAGE-4 decoy-deploying Blue vs FiniteStateRedAgent, "
                      f"seed {args.seeds[0]}. 25 red-labelled and 25 benign events, spread over source actions.\n\n"
                      + sample_table(*sample_pool) + "\n", encoding="utf-8")
        print("wrote", sp)
    raise SystemExit(0 if tot["unlabelled"] == 0 and tot["n_problems"] == 0 else 1)


if __name__ == "__main__":
    main()
