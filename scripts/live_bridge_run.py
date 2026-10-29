"""Run the telemetry bridge INSIDE a live CAGE-4 episode (T16, live-episode check).

Until now the bridge only read recorded dumps (scripts/dump_native_events.py). Here it is fed the raw observation
objects straight from env.get_observation(blue_agent) at every step, exactly as the experiment runner will.
Needs the CAGE-4 environment active (see docs/setup.md). Example:
  python scripts/live_bridge_run.py --seed 0 --blue decoy --compare results/native_events_decoy_seed0.jsonl

Checks printed at the end:
  * every native record became one event (decoy confirmations are not events), 0 unrecognised records
  * every event serialises to JSON (live observations carry IPv4Address objects, recorded dumps only strings)
  * if --compare is given: the live event stream equals the stream the bridge builds from the recorded dump
    (this also shows whether the simulator is deterministic for a given seed)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from dump_native_events import DecoyBlueAgent, EnterpriseGreenAgent, FiniteStateRedAgent, SleepAgent  # noqa: E402
from dump_native_events import EnterpriseScenarioGenerator, first_action  # noqa: E402
from CybORG import CybORG  # noqa: E402

from src.bridge import TelemetryBridge  # noqa: E402


def native_body(obs: dict) -> dict:
    """Same filter the runner will use: drop the wrapper's bookkeeping keys."""
    return {k: v for k, v in obs.items() if k not in ("success", "action")}


def count_records(blue_obs: dict) -> int:
    return sum(len(h.get("Processes", [])) for o in blue_obs.values() for h in o.values() if isinstance(h, dict))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--blue", choices=["sleep", "decoy"], default="sleep")
    ap.add_argument("--out", default=None, help="write the live events (to_log view) as JSONL")
    ap.add_argument("--compare", default=None, help="recorded dump of the same seed and Blue to compare against")
    args = ap.parse_args()

    blue_cls = DecoyBlueAgent if args.blue == "decoy" else SleepAgent
    sg = EnterpriseScenarioGenerator(blue_agent_class=blue_cls, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=FiniteStateRedAgent, steps=args.steps)
    env = CybORG(sg, "sim", seed=args.seed)
    env.reset()
    blue = [a for a in env.agents if a.startswith("blue")]

    bridge = TelemetryBridge(args.seed)
    live_events, n_records, n_confirmations, non_json = [], 0, 0, 0
    type_seen: set[str] = set()
    for step in range(args.steps):
        env.step()
        blue_obs = {}
        for a in blue:
            body = native_body(env.get_observation(a))
            if body:
                blue_obs[a] = body
        for o in blue_obs.values():
            for h in o.values():
                if isinstance(h, dict):
                    for p in h.get("Processes", []):
                        n_records += 1
                        n_confirmations += int("PPID" in p and "service_name" in p)
                        for c in p.get("Connections", []) or []:
                            for k in ("local_address", "remote_address"):
                                if k in c:
                                    type_seen.add(type(c[k]).__name__)
        events = bridge.step_events(step, blue_obs)
        for e in events:
            try:
                json.dumps(e.to_log())
            except TypeError:
                non_json += 1
        live_events.extend(events)

    print(f"seed {args.seed} blue={args.blue}: {len(live_events)} events from {n_records} native records "
          f"({n_confirmations} decoy confirmations), unknown records: {bridge.unknown_records}")
    print(f"address types in live observations: {sorted(type_seen)}; events that do not serialise to JSON: {non_json}")
    ok = bridge.unknown_records == 0 and len(live_events) == n_records - n_confirmations and non_json == 0
    print("record accounting:", "OK" if ok else "MISMATCH")

    if args.compare:
        rec_bridge = TelemetryBridge(args.seed)
        rec_events = []
        for line in pathlib.Path(args.compare).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rec_events.extend(rec_bridge.step_events(row["step"], row["blue_obs"]))
        live_log = [e.to_log() for e in live_events]
        rec_log = [e.to_log() for e in rec_events]
        same = live_log == rec_log
        print(f"compare with {args.compare}: recorded gives {len(rec_log)} events; live stream identical: {same}")
        if not same:
            for i, (a, b) in enumerate(zip(live_log, rec_log)):
                if a != b:
                    print("first difference at event", i, "\n live:", a, "\n rec :", b)
                    break
            else:
                print("one stream is a prefix of the other")

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for e in live_events:
                f.write(json.dumps(e.to_log()) + "\n")
        print("wrote", out)


if __name__ == "__main__":
    main()
