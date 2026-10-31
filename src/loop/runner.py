
"""Mock-first parallel experiment runner for T22."""

from __future__ import annotations

import argparse
import logging
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.loop.config import ExperimentConfig, load_config
from src.loop.logger import ExperimentLogger

logger = logging.getLogger(__name__)


@dataclass
class EpisodeResult:
    """Records and summary metrics produced by one episode."""

    seed: int
    round_number: int
    episode_number: int
    step_records: list[dict[str, Any]]
    reward: float


def run_mock_episode(
    config: ExperimentConfig,
    seed: int,
    round_number: int,
    episode_number: int,
    run_id: str,
) -> EpisodeResult:
    """Run a deterministic mock episode without real agents or CAGE-4."""
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    total_reward = 0.0

    for step in range(1, config.steps + 1):
        reward = rng.uniform(-1.0, 1.0)
        total_reward += reward

        records.append({
            "run_id": run_id,
            "condition": config.condition,
            "seed": seed,
            "round": round_number,
            "phase": "eval",
            "episode": episode_number,
            "step": step,
            "agent": "mock_agent",
            "action": None,
            "reward_components": {"mock_reward": reward},
            "alerts": [],
            "active_rules": [],
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "llm_calls": 0,
            "llm_latency_s": 0.0,
        })

    return EpisodeResult(
        seed=seed,
        round_number=round_number,
        episode_number=episode_number,
        step_records=records,
        reward=total_reward,
    )


def _run_episode(
    config: ExperimentConfig,
    seed: int,
    round_number: int,
    episode_number: int,
    run_id: str,
    episode_fn: Callable[..., EpisodeResult],
) -> EpisodeResult:
    """Execute one episode using the supplied episode implementation."""
    return episode_fn(
        config=config,
        seed=seed,
        round_number=round_number,
        episode_number=episode_number,
        run_id=run_id,
    )


def run_experiment(
    config: ExperimentConfig,
    output_path: str | Path,
    max_workers: int = 1,
    seed_set: str = "tuning",
    episode_fn: Callable[..., EpisodeResult] = run_mock_episode,
    round_extras_fn: Callable[[list[EpisodeResult]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run episodes over the selected configured seed set.

    round_extras_fn (optional, T28): called with the episode results of one (seed, round); the dict it returns is merged into
    that round's record, so real runs can fill precision, recall, fpr, ... instead of the mock's nulls. Default: unchanged.
    """
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1.")

    if seed_set == "tuning":
        selected_seeds = config.tuning_seeds
    elif seed_set == "test":
        selected_seeds = config.test_seeds
    else:
        raise ValueError("seed_set must be either 'tuning' or 'test'.")

    if not selected_seeds:
        raise ValueError(f"The configured {seed_set} seed list is empty.")

    run_id = str(uuid.uuid4())
    output_path = Path(output_path)
    results: list[EpisodeResult] = []

    jobs = [
        (seed, round_number, episode_number)
        for seed in selected_seeds
        for round_number in range(1, config.rounds + 1)
        for episode_number in range(config.episodes_per_round)
    ]

    logger.info(
        "Starting %s run %s with %d episodes across %d seeds",
        seed_set,
        run_id,
        len(jobs),
        len(selected_seeds),
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_episode,
                config,
                seed,
                round_number,
                episode_number,
                run_id,
                episode_fn,
            ): (seed, round_number, episode_number)
            for seed, round_number, episode_number in jobs
        }

        for future in as_completed(futures):
            seed, round_number, episode_number = futures[future]
            try:
                results.append(future.result())
            except Exception:
                logger.exception(
                    "Episode failed: seed=%d round=%d episode=%d",
                    seed,
                    round_number,
                    episode_number,
                )
                raise

    results.sort(
        key=lambda item: (
            item.seed,
            item.round_number,
            item.episode_number,
        )
    )

    with ExperimentLogger(output_path) as experiment_log:
        for result in results:
            for record in result.step_records:
                experiment_log.log_step(record)

        for seed in selected_seeds:
            for round_number in range(1, config.rounds + 1):
                round_results = [
                    item for item in results
                    if item.seed == seed and item.round_number == round_number
                ]

                mean_reward = (
                    sum(item.reward for item in round_results)
                    / len(round_results)
                )

                round_record = {
                    "run_id": run_id,
                    "condition": config.condition,
                    "seed": seed,
                    "round": round_number,
                    "rules_emitted": 0,
                    "rules_valid": 0,
                    "rule_validity": None,
                    "precision": None,
                    "recall": None,
                    "fpr": None,
                    "red_success": None,
                    "time_to_detect": None,
                    "mock_mean_reward": mean_reward,
                }
                if round_extras_fn is not None:
                    round_record.update(round_extras_fn(round_results))
                experiment_log.log_round(round_record)

    summary = {
        "run_id": run_id,
        "condition": config.condition,
        "seed_set": seed_set,
        "seeds": list(selected_seeds),
        "episodes_completed": len(results),
        "steps_logged": sum(len(item.step_records) for item in results),
        "rounds_completed": len(selected_seeds) * config.rounds,
        "output_path": str(output_path),
    }

    logger.info("Experiment completed: %s", summary)
    return summary


def run_from_yaml(
    config_path: str | Path,
    output_path: str | Path = "results/t22_experiment.jsonl",
    max_workers: int = 1,
    seed_set: str = "tuning",
) -> dict[str, Any]:
    """Load YAML configuration and execute the selected experiment."""
    config = load_config(config_path)
    return run_experiment(
        config=config,
        output_path=output_path,
        max_workers=max_workers,
        seed_set=seed_set,
    )


def main() -> None:
    """Command-line entry point for T22 experiments."""
    parser = argparse.ArgumentParser(
        description="Run a mock-first T22 experiment."
    )
    parser.add_argument("--config", default="configs/mock_experiment.yaml")
    parser.add_argument("--output", default="results/t22_experiment.jsonl")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--seed-set",
        choices=("tuning", "test"),
        default="tuning",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    run_from_yaml(
        config_path=args.config,
        output_path=args.output,
        max_workers=args.workers,
        seed_set=args.seed_set,
    )


if __name__ == "__main__":
    main()
