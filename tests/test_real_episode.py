"""T28: real CAGE-4 episodes (real Red + labeler + bridge + rules) through the T22 experiment runner."""
from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if CAGE4.exists():
    sys.path.insert(0, str(CAGE4))

pytest.importorskip("CybORG")
pytest.importorskip("ray")

from src.agents.red.mock_llm import MockRedLLM  # noqa: E402
from src.eval.summary import read_jsonl, split_records  # noqa: E402
from src.loop.config import load_config  # noqa: E402
from src.loop.logger import STEP_FIELDS  # noqa: E402
from src.loop.real_episode import (RealEpisodeRunner, RealEpisodeSettings, derive_env_seed, llm_sampling_seed,  # noqa: E402
                                   round_extras)
from src.loop.runner import run_experiment  # noqa: E402

CONFIG = ROOT / "configs" / "red_static_baseline.yaml"
RULES = str(ROOT / "configs" / "static_blue_rules.json")
STEPS = 60


@pytest.fixture
def runners():
    made = []

    def make(**kw):
        client = kw.pop("llm_client", None)
        r = RealEpisodeRunner(RealEpisodeSettings(**kw), llm_client=client)
        made.append(r)
        return r

    yield make
    for r in made:
        r.close()  # undo the CybORG patches so other tests see a clean CybORG


def config(**over):
    base = dict(steps=STEPS, rounds=1, episodes_per_round=1, tuning_seeds=(0,), test_seeds=(100,))
    base.update(over)
    return dataclasses.replace(load_config(CONFIG), **base)


def go(tmp_path, runner, cfg, name="log.jsonl", **kw):
    out = tmp_path / name
    summary = run_experiment(cfg, out, episode_fn=runner, round_extras_fn=round_extras, **kw)
    steps, rounds = split_records(read_jsonl(out))
    return summary, steps, rounds


def test_scripted_red_with_rules_end_to_end(tmp_path, runners):
    cfg = config(rounds=2)
    summary, steps, rounds = go(tmp_path, runners(red="aggressive", rules_path=RULES), cfg)
    assert summary["episodes_completed"] == 2
    assert len(steps) == 2 * (STEPS - 1)                       # CybORG ends an episode of N steps after N-1
    for r in steps:
        assert STEP_FIELDS <= r.keys() and {"tn", "events"} <= r.keys()
        assert r["phase"] == "eval" and r["agent"] == "env" and isinstance(r["action"], dict)
        assert "RedSessionCheck" not in r["action"].values() and "Sleep" not in r["action"].values()
        assert len(r["active_rules"]) == 10
    assert sum(r["tp"] + r["fn"] for r in steps) > 0           # Red produced events, all of them labelled
    assert sum(r["tp"] + r["fp"] for r in steps) > 0           # and the rules alerted
    assert len(rounds) == 2
    for r in rounds:
        assert r["rules_emitted"] == 10 and r["rule_validity"] == 1.0
        assert all(r[k] is not None for k in ("precision", "recall", "fpr"))
        assert 0 <= r["precision"] <= 1 and 0 <= r["recall"] <= 1 and 0 <= r["fpr"] <= 1
        assert r["tp"] + r["fp"] + r["fn"] + r["tn"] == r["events"]


def test_step_counts_add_up_to_the_round_record(tmp_path, runners):
    _, steps, rounds = go(tmp_path, runners(red="cage4_default", rules_path=RULES), config())
    (r,) = rounds
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == tuple(sum(s[k] for s in steps) for k in ("tp", "fp", "fn", "tn"))
    assert r["precision"] == pytest.approx(r["tp"] / (r["tp"] + r["fp"]))
    assert r["recall"] == pytest.approx(r["tp"] / (r["tp"] + r["fn"]))


def test_without_rules_nothing_alerts_and_undefined_metrics_are_null(tmp_path, runners):
    _, steps, (r,) = go(tmp_path, runners(red="cage4_default"), config())
    assert all(s["alerts"] == [] and s["active_rules"] == [] and s["tp"] == s["fp"] == 0 for s in steps)
    assert r["rules_emitted"] == 0 and r["rule_validity"] is None
    assert r["precision"] is None and r["recall"] == 0.0 and r["fpr"] == 0.0 and r["time_to_detect"] is None
    assert r["fn"] > 0                                          # Red events exist and none was caught


def test_runner_without_the_hook_still_writes_null_metrics(tmp_path, runners):
    out = tmp_path / "plain.jsonl"
    run_experiment(config(), out, episode_fn=runners(red="cage4_default", rules_path=RULES))   # no round_extras_fn
    (r,) = split_records(read_jsonl(out))[1]
    assert r["precision"] is None and r["rules_emitted"] == 0 and "mock_mean_reward" in r


def test_held_out_red_is_refused_on_tuning_seeds_and_allowed_on_test_seeds(tmp_path, runners):
    runner = runners(red="hit_and_run", rules_path=RULES)
    with pytest.raises(ValueError, match="held out"):
        go(tmp_path, runner, config(), seed_set="tuning")
    summary, steps, _ = go(tmp_path, runner, config(), name="test.jsonl", seed_set="test")
    assert summary["seeds"] == [100] and len(steps) == STEPS - 1


def test_same_config_gives_identical_logs(tmp_path, runners):
    runner = runners(red="stealthy", rules_path=RULES)
    _, a, ra = go(tmp_path, runner, config(), name="a.jsonl")
    _, b, rb = go(tmp_path, runner, config(), name="b.jsonl")
    strip = lambda recs: [{k: v for k, v in r.items() if k != "run_id"} for r in recs]  # noqa: E731
    assert strip(a) == strip(b) and strip(ra) == strip(rb)


def test_parallel_workers_are_serialised_and_give_the_same_result(tmp_path, runners):
    cfg = config(tuning_seeds=(0, 1), steps=40)
    runner = runners(red="cage4_default", rules_path=RULES)
    _, one, r1 = go(tmp_path, runner, cfg, name="w1.jsonl", max_workers=1)
    _, two, r2 = go(tmp_path, runner, cfg, name="w2.jsonl", max_workers=2)
    strip = lambda recs: [{k: v for k, v in r.items() if k != "run_id"} for r in recs]  # noqa: E731
    assert strip(one) == strip(two) and strip(r1) == strip(r2)


def test_env_seed_derivation():
    assert derive_env_seed(7, 1, 0) == 7                        # first episode of a seed = that CybORG seed
    derived = {derive_env_seed(s, r, e) for s in (0, 1, 100) for r in (1, 2, 3) for e in (0, 1, 2)} - {0, 1, 100}
    assert len(derived) == 3 * 3 * 3 - 3                        # all other episodes are distinct
    assert not derived & (set(range(10)) | set(range(100, 110)))  # and never collide with a configured seed


def test_llm_red_plans_per_round_keeps_memory_per_seed(tmp_path, runners):
    mem = tmp_path / "mem"
    runner = runners(red="llm", rules_path=RULES, memory_dir=str(mem), llm_client=MockRedLLM(seed=3))
    cfg = config(rounds=3, tuning_seeds=(0, 1), steps=40)
    summary, steps, rounds = go(tmp_path, runner, cfg)
    assert summary["episodes_completed"] == 6 and len(rounds) == 6
    assert {r["red_plan_source"] for r in rounds} <= {"llm", "llm_retry", "fallback"}
    for r in rounds:
        assert (r["red_plan"] is None) == (r["red_plan_source"] == "fallback")
    calls = [s["llm_calls"] for s in steps if s["step"] == 0]
    assert len(calls) == 6 and all(c >= 1 for c in calls) and all(s["llm_calls"] == 0 for s in steps if s["step"] > 0)
    for seed in (0, 1):                                          # a separate memory file per seed
        assert (mem / f"red_memory_seed{seed}.jsonl").exists()
    stored = [json.loads(line) for line in (mem / "red_memory_seed0.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert all({"round", "plan", "outcome"} <= e.keys() for e in stored) and len(stored) <= 2   # rounds 1-2 (round 3 not closed yet)


def test_llm_red_needs_rounds_in_order(tmp_path, runners):
    runner = runners(red="llm", rules_path=RULES, llm_client=MockRedLLM(seed=1))
    cfg = config()
    with pytest.raises(RuntimeError, match="in order"):
        runner(config=cfg, seed=0, round_number=2, episode_number=0, run_id="x")


def test_invalid_settings_are_rejected(runners):
    with pytest.raises(ValueError, match="blue"):
        RealEpisodeRunner(RealEpisodeSettings(blue="nope"))
    with pytest.raises(ValueError, match="red must be"):
        RealEpisodeRunner(RealEpisodeSettings(red="nope"))
    with pytest.raises(ValueError, match="llm_client"):
        RealEpisodeRunner(RealEpisodeSettings(red="llm"))


def test_every_seed_and_round_samples_the_llm_with_its_own_seed(tmp_path, runners):
    """Regression: one shared sampling seed made all seeds draw the same plan in the same round."""
    class Recording(MockRedLLM):
        seed = 0  # llama-server clients have a .seed attribute that the runner sets before each planning call

        def __init__(self):
            super().__init__(seed=5)
            self.used = []

        def generate(self, prompt, schema=None):
            self.used.append(self.seed)
            return super().generate(prompt, schema)

    client = Recording()
    runner = runners(red="llm", llm_client=client)
    go(tmp_path, runner, config(rounds=2, tuning_seeds=(0, 1), steps=30))
    # 2 seeds x 2 rounds -> 4 planning calls (a retry reuses the same seed), all four (seed, round) pairs distinct
    first_calls = []
    for seed in (0, 1):
        for rnd in (1, 2):
            first_calls.append(llm_sampling_seed(config().seed, seed, rnd))
    assert len(set(first_calls)) == 4
    assert set(first_calls) <= set(client.used) and len(set(client.used)) >= 4
    assert llm_sampling_seed(42, 0, 1) == llm_sampling_seed(42, 0, 1) != llm_sampling_seed(42, 1, 1)
