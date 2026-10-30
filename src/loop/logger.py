
"""Contract-compliant JSONL logging for T22 experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STEP_FIELDS = {
    "run_id", "condition", "seed", "round", "phase", "episode",
    "step", "agent", "action", "reward_components", "alerts",
    "active_rules", "tp", "fp", "fn", "llm_calls", "llm_latency_s",
}

ROUND_FIELDS = {
    "run_id", "condition", "seed", "round", "rules_emitted",
    "rules_valid", "rule_validity", "precision", "recall", "fpr",
    "red_success", "time_to_detect",
}

VALID_PHASES = {"red", "blue", "eval"}


class ExperimentLogger:
    """Append validated step-level and round-level records to JSONL files."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Start a fresh log for this logger instance.
        self.path.write_text("", encoding="utf-8")

    @staticmethod
    def _validate_fields(
        record: dict[str, Any], required: set[str], record_type: str
    ) -> None:
        missing = required - record.keys()
        if missing:
            raise ValueError(
                f"{record_type} record missing fields: {sorted(missing)}"
            )

    def _write(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
            )

    def log_step(self, record: dict[str, Any]) -> None:
        """Write one step-level record."""
        self._validate_fields(record, STEP_FIELDS, "Step")

        if record["phase"] not in VALID_PHASES:
            raise ValueError(
                f"Invalid phase '{record['phase']}'. "
                f"Expected one of {sorted(VALID_PHASES)}."
            )

        if not isinstance(record["reward_components"], dict):
            raise ValueError("'reward_components' must be a dictionary.")

        if not isinstance(record["alerts"], list):
            raise ValueError("'alerts' must be a list.")

        if not isinstance(record["active_rules"], list):
            raise ValueError("'active_rules' must be a list.")

        self._write(record)

    def log_round(self, record: dict[str, Any]) -> None:
        """Write one round-level record."""
        self._validate_fields(record, ROUND_FIELDS, "Round")
        self._write(record)

    def close(self) -> None:
        """No persistent file handle is held; provided for context-manager use."""
        return None

    def __enter__(self) -> ExperimentLogger:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
