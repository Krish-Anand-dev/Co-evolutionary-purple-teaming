"""Acceptance tests for the T24 mock co-evolution loop."""

import json

import pytest

from src.loop.config import ExperimentConfig
from src.loop.coevolution import run_coevolution


@pytest.fixture
def sample_config():
    return ExperimentConfig(
        condition="t24_test",
        seed=42,
        rounds=10,
        episodes_per_round=1,
        steps=1,
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


def test_ten_complete_coevolution_rounds(sample_config, tmp_path):
    output = tmp_path / "t24.jsonl"
    checkpoint = tmp_path / "t24_checkpoint.json"

    summary = run_coevolution(
        sample_config,
        output,
        checkpoint,
        rounds=10,
    )

    records = read_jsonl(output)
    round_records = [
        record for record in records if "red_reward_components" in record
    ]

    assert summary["rounds_completed"] == 10
    assert len(round_records) == 10
    assert [record["round"] for record in round_records] == list(range(1, 11))


def test_red_and_blue_phases_are_logged_separately(
    sample_config, tmp_path
):
    output = tmp_path / "phases.jsonl"
    checkpoint = tmp_path / "checkpoint.json"

    run_coevolution(sample_config, output, checkpoint, rounds=2)

    records = read_jsonl(output)
    phases = [record["phase"] for record in records if "phase" in record]

    assert phases == ["red", "blue", "red", "blue"]


def test_reward_components_are_logged_separately(
    sample_config, tmp_path
):
    output = tmp_path / "rewards.jsonl"
    checkpoint = tmp_path / "checkpoint.json"

    run_coevolution(sample_config, output, checkpoint, rounds=1)

    records = read_jsonl(output)
    red_record = next(r for r in records if r.get("phase") == "red")
    blue_record = next(r for r in records if r.get("phase") == "blue")

    assert {
        "kill_chain_progress",
        "time_to_detect",
        "red_reward",
    }.issubset(red_record["reward_components"])

    assert {
        "precision",
        "recall",
        "rule_validity",
        "fpr",
        "blue_reward",
    }.issubset(blue_record["reward_components"])


def test_blue_observes_updated_red_policy(sample_config, tmp_path):
    output = tmp_path / "policy.jsonl"
    checkpoint = tmp_path / "checkpoint.json"

    summary = run_coevolution(sample_config, output, checkpoint, rounds=3)

    assert summary["blue_state"]["red_policy_version_observed"] == 3


def test_checkpoint_resume_completes_remaining_rounds(
    sample_config, tmp_path, monkeypatch
):
    import src.loop.coevolution as coevolution

    output = tmp_path / "resume.jsonl"
    checkpoint = tmp_path / "resume_checkpoint.json"

    original_save = coevolution.save_checkpoint
    save_calls = 0

    def save_then_interrupt(path, state):
        nonlocal save_calls
        original_save(path, state)
        save_calls += 1
        if save_calls == 1:
            raise RuntimeError("Simulated interruption")

    monkeypatch.setattr(coevolution, "save_checkpoint", save_then_interrupt)

    with pytest.raises(RuntimeError, match="Simulated interruption"):
        run_coevolution(
            sample_config,
            output,
            checkpoint,
            rounds=4,
        )

    monkeypatch.setattr(coevolution, "save_checkpoint", original_save)

    summary = run_coevolution(
        sample_config,
        output,
        checkpoint,
        rounds=4,
        resume=True,
    )

    records = read_jsonl(output)
    round_records = [
        record for record in records if "red_reward_components" in record
    ]

    assert summary["rounds_completed"] == 4
    assert len(round_records) == 4
    assert [record["round"] for record in round_records] == [1, 2, 3, 4]
def test_resume_discards_uncheckpointed_log_round(
    sample_config, tmp_path, monkeypatch
):
    import src.loop.coevolution as coevolution

    output = tmp_path / "crash_recovery.jsonl"
    checkpoint = tmp_path / "crash_recovery_checkpoint.json"

    original_save = coevolution.save_checkpoint
    save_calls = 0

    def interrupt_before_second_checkpoint(path, state):
        nonlocal save_calls
        save_calls += 1
        if save_calls == 2:
            raise RuntimeError("Crash before checkpoint save")
        original_save(path, state)

    monkeypatch.setattr(
        coevolution, "save_checkpoint", interrupt_before_second_checkpoint
    )

    with pytest.raises(RuntimeError, match="Crash before checkpoint save"):
        run_coevolution(sample_config, output, checkpoint, rounds=4)

    monkeypatch.setattr(coevolution, "save_checkpoint", original_save)

    summary = run_coevolution(
        sample_config, output, checkpoint, rounds=4, resume=True
    )

    records = read_jsonl(output)
    round_records = [
        record for record in records if "red_reward_components" in record
    ]

    assert summary["rounds_completed"] == 4
    assert [record["round"] for record in round_records] == [1, 2, 3, 4]
    assert len(round_records) == 4
