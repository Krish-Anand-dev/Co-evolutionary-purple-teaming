"""Mock Red agent: plays a uniformly random legal CAGE-4 action every step (T07).

CybORG builds Red agents itself as ``cls(name, np_random=...)`` and calls
``get_action(observation, action_space)`` each step, so those two signatures are fixed.
Contract (RedAgent API): reset(seed), act(obs), plan(round_ctx), update(trajectories).
``act`` also needs the action space because CybORG's legal actions depend on the current state.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import numpy as np
from CybORG.Agents.SimpleAgents.BaseAgent import BaseAgent
from CybORG.Simulator.Actions import Sleep

from src.agents.red.legality import is_legal, legal_commands

log = logging.getLogger(__name__)


class RandomRed(BaseAgent):
    def __init__(self, name: str, np_random=None):
        super().__init__(name, np_random=np_random)
        self.action_counts: Counter[str] = Counter()
        self.illegal_count = 0
        self.steps = 0

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.np_random = np.random.default_rng(seed)
        self.action_counts.clear()
        self.illegal_count = 0
        self.steps = 0

    def act(self, obs: Any, action_space: dict) -> Any:
        commands = legal_commands(action_space)
        if not commands:
            return Sleep()
        name = list(commands)[int(self.np_random.integers(len(commands)))]
        options = dict(commands[name])
        cls = options.pop("command")
        params = {p: values[int(self.np_random.integers(len(values)))] for p, values in options.items()}
        action = cls(**params)
        ok, reason = is_legal(action, action_space)
        if not ok:  # should be unreachable; count it and fall back so an episode never crashes
            self.illegal_count += 1
            log.warning("%s produced an illegal action (%s); playing Sleep", self.name, reason)
            action = Sleep()
        self.action_counts[type(action).__name__] += 1
        self.steps += 1
        return action

    def get_action(self, observation, action_space):
        return self.act(observation, action_space)

    def plan(self, round_ctx: dict) -> dict:
        return {}

    def update(self, trajectories) -> None:
        pass

    def train(self, results):
        pass

    def end_episode(self):
        pass

    def set_initial_values(self, action_space, observation):
        pass
