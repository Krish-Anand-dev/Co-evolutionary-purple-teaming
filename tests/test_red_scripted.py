"""T19 scripted Red variants: table sanity, no stranded agents, strategies really differ, held-out kept apart."""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if CAGE4.exists():
    sys.path.insert(0, str(CAGE4))

pytest.importorskip("CybORG")
pytest.importorskip("ray")

from src.agents.red import scripted  # noqa: E402

NAMES = ["DiscoverRemoteSystems", "AggressiveServiceDiscovery", "StealthServiceDiscovery", "DiscoverDeception",
         "ExploitRemoteService", "PrivilegeEscalate", "Impact", "DegradeServices", "Withdraw"]


def make(cls):
    import numpy as np
    return cls("red_agent_0", np_random=np.random.default_rng(0), agent_subnets=[])


@pytest.mark.parametrize("name", list(scripted.ALL))
def test_every_row_sums_to_one(name):
    table = make(scripted.ALL[name]).state_transitions_probability
    for state, row in table.items():
        assert len(row) == len(NAMES), (name, state)
        assert abs(sum(v for v in row if v is not None) - 1.0) < 1e-9, (name, state)


def test_registry_keeps_held_out_apart():
    assert set(scripted.HELD_OUT) == {"hit_and_run"}
    assert not set(scripted.HELD_OUT) & set(scripted.TRAINING)
    assert len(scripted.TRAINING) >= 3


def test_aggressive_and_stealthy_use_different_scans():
    agg = make(scripted.AggressiveRed).state_transitions_probability
    ste = make(scripted.StealthyRed).state_transitions_probability
    assert all(r[2] is None for r in agg.values()) and any(r[1] for r in agg.values())
    assert all(r[1] is None for r in ste.values()) and any(r[2] for r in ste.values())


def test_hit_and_run_never_offers_withdraw_with_a_single_shell_host():
    agent = make(scripted.HitAndRunRed)
    assert any(r[8] for r in agent._with_withdraw.values())
    assert all(r[8] is None for r in agent._without_withdraw.values())
    for row in agent._without_withdraw.values():
        assert abs(sum(v for v in row if v is not None) - 1.0) < 1e-9


@pytest.mark.parametrize("name", ["aggressive", "stealthy", "deception_aware", "hit_and_run"])
def test_variant_keeps_acting_through_a_short_episode(name):
    """Regression: hit_and_run once withdrew from its only host and then slept for the whole episode."""
    from CybORG import CybORG
    from CybORG.Agents import EnterpriseGreenAgent, SleepAgent
    from CybORG.Simulator.Scenarios import EnterpriseScenarioGenerator

    sg = EnterpriseScenarioGenerator(blue_agent_class=SleepAgent, green_agent_class=EnterpriseGreenAgent,
                                     red_agent_class=scripted.ALL[name], steps=120)
    env = CybORG(sg, "sim", seed=1)  # seed 1 was one of the stranding seeds
    env.reset()
    red = [a for a in env.agents if a.startswith("red")]
    acted = 0
    for _ in range(119):
        env.step()
        for a in red:
            last = env.get_last_action(a)
            last = last[0] if isinstance(last, (list, tuple)) and last else last
            acted += type(last).__name__ != "Sleep"
    assert acted > 50, f"{name} barely acted ({acted} non-Sleep actions)"
