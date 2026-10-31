"""Scripted Blue baseline that deploys a decoy on every non-router host it can reach, one per decision, then sleeps (T28).

Same behaviour as DecoyBlueAgent in scripts/dump_native_events.py (T12/T16 evidence); here it lives in src so the experiment
runner can use it. It is a stand-in until the real Blue (T27) is wired in: it creates the decoy confirmations and decoy-hit
events the bridge has to handle, but it does not react to alerts.
"""
from __future__ import annotations

from CybORG.Agents.SimpleAgents.BaseAgent import BaseAgent
from CybORG.Simulator.Actions import DeployDecoy, Sleep


class DecoyBlue(BaseAgent):
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
