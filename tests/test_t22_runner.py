
"""Tests for the T22 mock-first experiment runner."""

import json

import pytest

from src.loop.config import ExperimentConfig
from src.loop.runner import run_experiment, run_mock_episode


@pytest.fixture
def sample_config() -> ExperimentConfig:
    return ExperimentConfig(
        condition="test_condition",
        seed=42,
        rounds=2,
        episodes_per_round=2,
        steps=3,
        llm_model="mock",
        temperature=0.0,
        noise_level=0.0,
        alpha1=1.0,
        alpha2=1.0,
        beta1=1.0,
        beta2=1.0,
        beta3=1.0,
        beta4=1.0,
        playbook={},
        tuning_seeds=(0, 1),
        test_seeds=(100, 101),
    )


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def test_tuning_run_uses_only_tuning_seeds(sample_config, tmp_path):
    output = tmp_path / "tuning.jsonl"

    summary = run_experiment(
        sample_config,
        output,
        max_workers=2,
        seed_set="tuning",
    )

    records = read_jsonl(output)

    assert summary["seeds"] == [0, 1]
    assert summary["episodes_completed"] == 8
    assert summary["steps_logged"] == 24
    assert summary["rounds_completed"] == 4

    assert len(records) == 28
    assert {record["seed"] for record in records} == {0, 1}


def test_test_run_uses_only_test_seeds(sample_config, tmp_path):
    output = tmp_path / "test.jsonl"

    summary = run_experiment(
        sample_config,
        output,
        max_workers=2,
        seed_set="test",
    )

    records = read_jsonl(output)

    assert summary["seeds"] == [100, 101]
    assert summary["episodes_completed"] == 8
    assert summary["steps_logged"] == 24
    assert summary["rounds_completed"] == 4

    assert len(records) == 28
    assert {record["seed"] for record in records} == {100, 101}


def test_invalid_seed_set_is_rejected(sample_config, tmp_path):
    with pytest.raises(ValueError, match="seed_set"):
        run_experiment(
            sample_config,
            tmp_path / "invalid.jsonl",
            seed_set="unknown",
        )


def test_empty_seed_set_is_rejected(sample_config, tmp_path):
    empty_config = ExperimentConfig(
        **{
            **sample_config.__dict__,
            "tuning_seeds": (),
        }
    )

    with pytest.raises(ValueError, match="empty"):
        run_experiment(
            empty_config,
            tmp_path / "empty.jsonl",
            seed_set="tuning",
        )


def test_mock_episode_is_reproducible(sample_config):
    first = run_mock_episode(
        sample_config, 42, 1, 0, "run-1"
    )
    second = run_mock_episode(
        sample_config, 42, 1, 0, "run-2"
    )

    assert first.reward == second.reward
    assert first.step_records[0]["reward_components"] == (
        second.step_records[0]["reward_components"]
    )


def test_invalid_worker_count_is_rejected(sample_config, tmp_path):
    with pytest.raises(ValueError, match="max_workers"):
        run_experiment(
            sample_config,
            tmp_path / "invalid_workers.jsonl",
            max_workers=0,
        )
def test_round_extras_callback_is_logged(sample_config, tmp_path):
    output = tmp_path / "extras.jsonl"
    callback_calls = []

    def round_extras(round_results):
        callback_calls.append(round_results)
        return {
            "precision": 0.75,
            "recall": 0.60,
            "fpr": 0.10,
        }

    run_experiment(
        sample_config,
        output,
        round_extras_fn=round_extras,
    )

    records = read_jsonl(output)
    round_records = [
        record for record in records
        if "mock_mean_reward" in record
    ]

    assert len(callback_calls) == 4
    assert len(round_records) == 4

    for record in round_records:
        assert record["precision"] == 0.75
        assert record["recall"] == 0.60
        assert record["fpr"] == 0.10
