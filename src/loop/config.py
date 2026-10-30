
"""Experiment configuration loading and validation for T22."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExperimentConfig:
    condition: str
    seed: int
    rounds: int
    episodes_per_round: int
    steps: int
    llm_model: str
    temperature: float
    noise_level: float
    alpha1: float
    alpha2: float
    beta1: float
    beta2: float
    beta3: float
    beta4: float
    playbook: dict[str, Any]
    tuning_seeds: tuple[int, ...]
    test_seeds: tuple[int, ...]

    @property
    def total_episodes(self) -> int:
        return self.rounds * self.episodes_per_round


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a YAML mapping.")
    return value


def _require_int(data: dict[str, Any], key: str, minimum: int = 0) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"'{key}' must be an integer >= {minimum}.")
    return value


def _require_number(data: dict[str, Any], key: str, minimum: float = 0.0) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{key}' must be a number.")
    result = float(value)
    if result < minimum:
        raise ValueError(f"'{key}' must be >= {minimum}.")
    return result


def load_config(path: str | Path) -> ExperimentConfig:
    """Load a YAML experiment configuration and validate its fields."""
    config_path = Path(path)

    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML configuration: {exc}") from exc

    data = _require_mapping(raw, "Configuration")

    condition = data.get("condition")
    if not isinstance(condition, str) or not condition.strip():
        raise ValueError("'condition' must be a non-empty string.")

    llm_model = data.get("llm_model")
    if not isinstance(llm_model, str) or not llm_model.strip():
        raise ValueError("'llm_model' must be a non-empty string.")

    playbook = _require_mapping(data.get("playbook", {}), "playbook")

    tuning = data.get("tuning_seeds", list(range(10)))
    testing = data.get("test_seeds", list(range(100, 110)))

    if not isinstance(tuning, list) or not all(
        isinstance(seed, int) and not isinstance(seed, bool) for seed in tuning
    ):
        raise ValueError("'tuning_seeds' must be a list of integers.")

    if not isinstance(testing, list) or not all(
        isinstance(seed, int) and not isinstance(seed, bool) for seed in testing
    ):
        raise ValueError("'test_seeds' must be a list of integers.")

    if len(set(tuning)) != len(tuning) or len(set(testing)) != len(testing):
        raise ValueError("Seed lists must not contain duplicates.")

    overlap = set(tuning) & set(testing)
    if overlap:
        raise ValueError(f"Tuning and test seeds must be separate: {sorted(overlap)}")

    noise = _require_number(data, "noise_level")
    if noise > 1.0:
        raise ValueError("'noise_level' must be between 0 and 1.")

    temperature = _require_number(data, "temperature")
    if temperature > 2.0:
        raise ValueError("'temperature' must be between 0 and 2.")

    return ExperimentConfig(
        condition=condition.strip(),
        seed=_require_int(data, "seed"),
        rounds=_require_int(data, "rounds", 1),
        episodes_per_round=_require_int(data, "episodes_per_round", 1),
        steps=_require_int(data, "steps", 1),
        llm_model=llm_model.strip(),
        temperature=temperature,
        noise_level=noise,
        alpha1=_require_number(data, "alpha1"),
        alpha2=_require_number(data, "alpha2"),
        beta1=_require_number(data, "beta1"),
        beta2=_require_number(data, "beta2"),
        beta3=_require_number(data, "beta3"),
        beta4=_require_number(data, "beta4"),
        playbook=playbook,
        tuning_seeds=tuple(tuning),
        test_seeds=tuple(testing),
    )
