"""T07 mock agents: legality checker, RandomRed, RandomBlue, and a short live CAGE-4 episode."""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import numpy as np
import pytest

from src.agents.baselines.random_blue import RandomBlue
from src.agents.red.legality import is_legal, legal_commands

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if CAGE4.exists():  # same path trick the scripts use; `pip install -e .` does not put CybORG on sys.path
    sys.path.insert(0, str(CAGE4))


class Scan:
    def __init__(self, session, ip_address):
        self.session, self.ip_address = session, ip_address


class Wait:
    def __init__(self):
        pass


def fake_space():
    return {
        "action": {Scan: True, Wait: True},
        "session": {0: True, 1: False},
        "ip_address": {"10.0.0.1": True, "10.0.0.2": False, "10.0.0.3": True},
    }


def test_legal_commands_lists_only_allowed_values():
    cmds = legal_commands(fake_space())
    assert cmds["Scan"]["session"] == [0]
    assert cmds["Scan"]["ip_address"] == ["10.0.0.1", "10.0.0.3"]
    assert "command" in cmds["Wait"]


def test_class_with_no_allowed_value_is_dropped():
    space = fake_space()
    space["session"] = {0: False}
    assert "Scan" not in legal_commands(space)
    space["action"][Wait] = False
    assert legal_commands(space) == {}


def test_is_legal_flags_bad_class_and_bad_param():
    space = fake_space()
    assert is_legal(Scan(0, "10.0.0.1"), space)[0]
    ok, reason = is_legal(Scan(1, "10.0.0.1"), space)
    assert not ok and "session" in reason
    ok, reason = is_legal(Scan(0, "10.0.0.2"), space)
    assert not ok and "ip_address" in reason
    space["action"][Wait] = False
    assert not is_legal(Wait(), space)[0]


def test_random_blue_respects_mask_and_seed():
    mask = np.zeros(20, dtype=bool)
    mask[[3, 7, 19]] = True
    a = RandomBlue("blue_agent_0", seed=5)
    picks = [a.act(20, mask) for _ in range(200)]
    assert set(picks) <= {3, 7, 19} and len(set(picks)) == 3
    b = RandomBlue("blue_agent_0", seed=5)
    assert picks == [b.act(20, mask) for _ in range(200)]
    b.reset(5)
    assert picks == [b.act(20, mask) for _ in range(200)]


def test_random_blue_without_mask_and_empty_mask():
    a = RandomBlue("blue_agent_1", seed=0)
    assert 0 <= a.act(5) < 5
    assert a.act(5, np.zeros(5, dtype=bool)) == 4  # falls back to the last index (Sleep)
    assert a.illegal_count == 1


def test_random_red_only_plays_legal_actions():
    pytest.importorskip("CybORG")
    from src.agents.baselines.random_red import RandomRed

    space = fake_space()
    red = RandomRed("red_agent_0", np_random=np.random.default_rng(1))
    for _ in range(300):
        assert is_legal(red.act({}, space), space)[0]
    assert red.illegal_count == 0 and red.steps == 300
    assert {"Scan", "Wait"} <= set(red.action_counts)


def test_live_episode_has_no_illegal_actions():
    pytest.importorskip("CybORG")
    pytest.importorskip("ray")
    spec = importlib.util.spec_from_file_location("hello_agents", ROOT / "scripts" / "hello_agents.py")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except SystemExit:
        pytest.skip("CAGE-4 not cloned to external/cage-challenge-4")
    summary = module.run_episode(seed=0, steps=40)
    assert summary["full_episode"]
    assert summary["red"]["agents_that_acted"] > 0
    assert summary["red"]["illegal_rejected_by_agent"] == 0
    assert summary["red"]["invalid_action_recorded_by_env"] == 0
    assert summary["blue"]["chosen_outside_action_mask"] == 0
