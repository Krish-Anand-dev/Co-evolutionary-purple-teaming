from __future__ import annotations

from CybORG import CybORG
from CybORG.Agents import BaseAgent

from ray.rllib.env.multi_agent_env import MultiAgentEnv
from CybORG.Agents.Wrappers.EnterpriseMAE import EnterpriseMAE

# Import your custom agents here.
from dummy_agent import DummyAgent


# Copy of CybORG/Evaluation/example_submission/submission.py with the
# `from __future__` import moved to the top (upstream raises a SyntaxError).
class Submission:
    NAME: str = "Dummy baseline"
    TEAM: str = "MAIT purple team"
    TECHNIQUE: str = "Last-action dummy"

    AGENTS: dict[str, BaseAgent] = {
        f"blue_agent_{agent}": DummyAgent() for agent in range(5)
    }

    def wrap(env: CybORG) -> MultiAgentEnv:
        return EnterpriseMAE(env)
