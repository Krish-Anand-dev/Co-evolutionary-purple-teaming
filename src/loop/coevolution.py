"""Mock-first Red/Blue co-evolution loop for T24."""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

from src.loop.checkpoint import load_checkpoint, save_checkpoint
from src.loop.config import ExperimentConfig



def _red_phase(
    config: ExperimentConfig,
    seed: int,
    round_number: int,
    red_state: dict[str, Any],
    run_id: str,
) -> tuple[dict[str, Any], dict[str, float], list[dict[str, Any]]]:
    """Run one deterministic mock Red phase."""
    rng = random.Random(seed + round_number * 1009)

    kill_chain_progress = round(rng.uniform(0.2, 1.0), 4)
    time_to_detect = round(rng.uniform(0.1, 1.0), 4)

    reward = (
        config.alpha1 * kill_chain_progress
        - config.alpha2 * time_to_detect
    )

    components = {
        "kill_chain_progress": kill_chain_progress,
        "time_to_detect": time_to_detect,
        "red_reward": round(reward, 4),
    }

    updated_state = {
        **red_state,
        "policy_version": round_number,
        "last_reward": round(reward, 4),
    }

    record = {
        "run_id": run_id,
        "condition": config.condition,
        "seed": seed,
        "round": round_number,
        "phase": "red",
        "episode": 0,
        "step": 1,
        "agent": "mock_red",
        "action": "mock_attack",
        "reward_components": components,
        "alerts": [],
        "active_rules": [],
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "llm_calls": 0,
        "llm_latency_s": 0.0,
    }

    return updated_state, components, [record]


def _blue_phase(
    config: ExperimentConfig,
    seed: int,
    round_number: int,
    red_state: dict[str, Any],
    blue_state: dict[str, Any],
    run_id: str,
) -> tuple[dict[str, Any], dict[str, float], list[dict[str, Any]]]:
    """Run one deterministic mock Blue phase against the updated Red state."""
    rng = random.Random(seed + round_number * 2027)

    precision = round(rng.uniform(0.5, 1.0), 4)
    recall = round(rng.uniform(0.5, 1.0), 4)
    rule_validity = round(rng.uniform(0.5, 1.0), 4)
    fpr = round(rng.uniform(0.0, 0.3), 4)

    reward = (
        config.beta1 * precision
        + config.beta2 * recall
        + config.beta3 * rule_validity
        - config.beta4 * fpr
    )

    components = {
        "precision": precision,
        "recall": recall,
        "rule_validity": rule_validity,
        "fpr": fpr,
        "blue_reward": round(reward, 4),
    }

    updated_state = {
        **blue_state,
        "policy_version": round_number,
        "last_reward": round(reward, 4),
        "red_policy_version_observed": red_state["policy_version"],
    }

    record = {
        "run_id": run_id,
        "condition": config.condition,
        "seed": seed,
        "round": round_number,
        "phase": "blue",
        "episode": 0,
        "step": 1,
        "agent": "mock_blue",
        "action": "mock_rule_update",
        "reward_components": components,
        "alerts": [],
        "active_rules": [],
        "tp": 0,
        "fp": 0,
        "fn": 0,
        "llm_calls": 0,
        "llm_latency_s": 0.0,
    }

    return updated_state, components, [record]


def run_coevolution(
    config: ExperimentConfig,
    output_path: str | Path,
    checkpoint_path: str | Path,
    rounds: int = 10,
    seed: int | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run sequential mock Red/Blue phases, saving state after each round."""
    if isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1:
        raise ValueError("rounds must be an integer >= 1.")

    run_seed = config.seed if seed is None else seed
    if isinstance(run_seed, bool) or not isinstance(run_seed, int):
        raise ValueError("seed must be an integer.")

    output_path = Path(output_path)
    checkpoint_path = Path(checkpoint_path)

    if resume:
        state = load_checkpoint(checkpoint_path)

        if state.get("condition") != config.condition:
            raise ValueError("Checkpoint condition does not match config.")
        if state.get("seed") != run_seed:
            raise ValueError("Checkpoint seed does not match requested seed.")
        if state.get("total_rounds") != rounds:
            raise ValueError("Checkpoint round count does not match request.")

        completed_rounds = state["completed_rounds"]
        red_state = state["red_state"]
        blue_state = state["blue_state"]
        run_id = state["run_id"]
        history = state["history"]

        if not output_path.is_file():
            raise FileNotFoundError(
                "Cannot resume: the original JSONL log is missing."
            )

        # Discard log records from rounds not committed in the checkpoint.
        committed_lines = []
        with output_path.open("r", encoding="utf-8") as log_file:
            for line in log_file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    # Ignore an incomplete or corrupted trailing record.
                    continue

                if record.get("run_id") != run_id:
                    raise ValueError("JSONL log contains a different run ID.")

                if record.get("round", 0) <= completed_rounds:
                    committed_lines.append(line)

        with output_path.open("w", encoding="utf-8") as log_file:
            log_file.writelines(committed_lines)
    else:
        if checkpoint_path.exists():
            raise FileExistsError(
                "Checkpoint already exists. Use resume=True or choose "
                "a different checkpoint path."
            )

        if output_path.exists():
            raise FileExistsError(
                "Output log already exists. Choose a new output path."
            )

        completed_rounds = 0
        red_state = {"policy_version": 0, "last_reward": None}
        blue_state = {"policy_version": 0, "last_reward": None}
        run_id = str(uuid.uuid4())
        history: list[dict[str, Any]] = []

    with output_path.open("a", encoding="utf-8") as log_file:
        for round_number in range(completed_rounds + 1, rounds + 1):
            red_state, red_components, red_records = _red_phase(
                config,
                run_seed,
                round_number,
                red_state,
                run_id,
            )

            blue_state, blue_components, blue_records = _blue_phase(
                config,
                run_seed,
                round_number,
                red_state,
                blue_state,
                run_id,
            )

            for record in red_records + blue_records:
                log_file.write(json.dumps(record, allow_nan=False) + "\n")

            round_record = {
                "run_id": run_id,
                "condition": config.condition,
                "seed": run_seed,
                "round": round_number,
                "rules_emitted": 0,
                "rules_valid": 0,
                "rule_validity": blue_components["rule_validity"],
                "precision": blue_components["precision"],
                "recall": blue_components["recall"],
                "fpr": blue_components["fpr"],
                "red_success": red_components["kill_chain_progress"],
                "time_to_detect": red_components["time_to_detect"],
                "red_reward_components": red_components,
                "blue_reward_components": blue_components,
            }

            log_file.write(json.dumps(round_record, allow_nan=False) + "\n")
            log_file.flush()

            completed_rounds = round_number
            history.append(round_record)

            save_checkpoint(
                checkpoint_path,
                {
                    "condition": config.condition,
                    "seed": run_seed,
                    "total_rounds": rounds,
                    "completed_rounds": completed_rounds,
                    "red_state": red_state,
                    "blue_state": blue_state,
                    "run_id": run_id,
                    "history": history,
                },
            )

    return {
        "run_id": run_id,
        "condition": config.condition,
        "seed": run_seed,
        "rounds_completed": completed_rounds,
        "red_state": red_state,
        "blue_state": blue_state,
        "output_path": str(output_path),
        "checkpoint_path": str(checkpoint_path),
    }