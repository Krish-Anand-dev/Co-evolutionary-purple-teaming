"""Mock Blue agent: plays a uniformly random legal action index every step (T07).

Blue is driven through CybORG's wrapper (``EnterpriseMAE``), where each agent gets a flat vector and
picks an action *index*. ``info[agent]["action_mask"]`` marks which indices are real this episode
(hosts that do not exist are mapped to Sleep). Contract (BlueAgent API): reset(seed), observe, act, ...
This mock only needs reset / act; the real Blue lives in src/agents/blue/.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np


class RandomBlue:
    def __init__(self, name: str, seed: int | None = None):
        self.name = name
        self.rng = np.random.default_rng(seed)
        self.action_counts: Counter[int] = Counter()
        self.illegal_count = 0
        self.steps = 0

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.action_counts.clear()
        self.illegal_count = 0
        self.steps = 0

    def act(self, n_actions: int, action_mask: Any = None) -> int:
        """Uniform choice among indices the mask marks legal (all of them when no mask is given)."""
        if action_mask is None:
            legal = np.arange(n_actions)
        else:
            legal = np.flatnonzero(np.asarray(action_mask, dtype=bool))
        if legal.size == 0:  # should not happen; the last index is Sleep in CAGE-4
            self.illegal_count += 1
            legal = np.array([n_actions - 1])
        action = int(self.rng.choice(legal))
        self.action_counts[action] += 1
        self.steps += 1
        return action
