"""Dump what CAGE-4 natively gives Blue each step, next to what Red and Green just did (T12 evidence).

Run with the CAGE-4 venv (NOT the main venv):
  .venv-cyborg\\Scripts\\python scripts\\dump_native_events.py --seed 0 --steps 500 --out results/native_events_seed0.jsonl

Blue agents are SleepAgents (they never act), Red is FiniteStateRedAgent, Green is EnterpriseGreenAgent, i.e. the
default evaluation setup. One JSON line per step. Nothing here modifies CybORG.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "cage-challenge-4-main"))

from CybORG import CybORG  # noqa: E402
from CybORG.Agents import EnterpriseGreenAgent, FiniteStateRedAgent, SleepAgent  # noqa: E402
from CybORG.Agents.SimpleAgents.BaseAgent import BaseAgent  # noqa: E402
from CybORG.Simulator.Actions import DeployDecoy, Sleep  # noqa: E402
from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator  # noqa: E402


class DecoyBlueAgent(BaseAgent):
    """Deploys a decoy on every non-router host it can reach, one per decision, then sleeps.
    Used only to see what decoy interactions look like in Blue's native observations."""

    def __init__(self, name=None, **kwargs):
        super().__init__(name)
        self.done: set[str] = set()

    def get_action(self, observation, action_space):
        hosts = sorted(h for h, ok in action_space["hostname"].items() if ok and "router" not in h)
        for host in hosts:
            if host not in self.done:
                self.done.add(host)
                return DeployDecoy(session=0, agent=self.name, hostname=host)
        return Sleep()

    def train(self, results):
        pass

    def end_episode(self):
        self.done.clear()

    def set_initial_values(self, action_space, observation):
        pass


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)           # IPv4Address, enums, ...


def first_action(raw):
    """env.get_last_action returns a list like [Sleep]; take its first element."""
    if isinstance(raw, (list, tuple)):
        return raw[0] if raw else None
    return raw


def action_name(action) -> str:
    return type(action).__name__


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--out", default="results/native_events_seed0.jsonl")
    ap.add_argument("--blue", choices=["sleep", "decoy"], default="sleep", help="Blue behaviour (default: passive)")
    args = ap.parse_args()

    blue_cls = DecoyBlueAgent if args.blue == "decoy" else SleepAgent
    sg = EnterpriseScenarioGenerator(blue_agent_class=blue_cls, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=FiniteStateRedAgent, steps=args.steps)
    env = CybORG(sg, "sim", seed=args.seed)
    env.reset()
    agents = list(env.agents)
    blue = [a for a in agents if a.startswith("blue")]
    red = [a for a in agents if a.startswith("red")]
    green = [a for a in agents if a.startswith("green")]

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for step in range(args.steps):
            env.step()
            red_actions = {}
            for a in red:
                act = first_action(env.get_last_action(a))
                if act is None or type(act).__name__ == "Sleep":
                    continue
                obs = env.get_observation(a)
                red_actions[a] = {"action": str(act), "type": action_name(act), "success": str(obs.get("success"))}
            green_actions: dict[str, int] = {}
            for a in green:
                act = first_action(env.get_last_action(a))
                if act is not None and type(act).__name__ != "Sleep":
                    green_actions[action_name(act)] = green_actions.get(action_name(act), 0) + 1
            blue_actions = {}
            for a in blue:
                bact = first_action(env.get_last_action(a))
                if bact is not None and type(bact).__name__ not in ("Sleep", "Monitor"):
                    blue_actions[a] = str(bact)
            blue_obs = {}
            for a in blue:
                obs = env.get_observation(a)
                body = {k: v for k, v in obs.items() if k not in ("success", "action")}
                if body:
                    blue_obs[a] = jsonable(body)
            f.write(json.dumps({"step": step, "phase": getattr(env.environment_controller.state, "mission_phase", None),
                                "red": red_actions, "green": green_actions, "blue_actions": blue_actions,
                                "blue_obs": blue_obs}) + "\n")
    print(f"wrote {args.steps} steps to {out}")


if __name__ == "__main__":
    main()
