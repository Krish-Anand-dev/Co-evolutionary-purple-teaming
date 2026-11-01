"""Checkpoint save/load utilities for the T24 co-evolution loop."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CHECKPOINT_VERSION = 1


def save_checkpoint(
    path: str | Path,
    state: dict[str, Any],
) -> None:
    """Save loop state atomically so an interrupted write won't corrupt it."""
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": CHECKPOINT_VERSION,
        "state": state,
    }

    temporary_path = checkpoint_path.with_suffix(
        checkpoint_path.suffix + ".tmp"
    )

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(
                payload,
                file,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            file.flush()
            os.fsync(file.fileno())

        temporary_path.replace(checkpoint_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    """Load and validate a previously saved T24 checkpoint."""
    checkpoint_path = Path(path)

    if not checkpoint_path.is_file():
        raise FileNotFoundError(
            f"Checkpoint file not found: {checkpoint_path}"
        )

    with checkpoint_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError("Checkpoint must contain a JSON object.")

    if payload.get("version") != CHECKPOINT_VERSION:
        raise ValueError("Unsupported checkpoint version.")

    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("Checkpoint state must be a JSON object.")

    if (
        isinstance(state.get("completed_rounds"), bool)
        or not isinstance(state.get("completed_rounds"), int)
        or state["completed_rounds"] < 0
    ):
        raise ValueError(
            "'completed_rounds' must be a non-negative integer."
        )

    return state