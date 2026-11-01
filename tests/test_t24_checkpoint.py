"""Tests for T24 checkpoint save/load utilities."""

import json

import pytest

from src.loop.checkpoint import load_checkpoint, save_checkpoint


def test_checkpoint_round_trip(tmp_path):
    path = tmp_path / "checkpoint.json"
    state = {
        "completed_rounds": 5,
        "red_state": {"policy_version": 5},
        "blue_state": {"policy_version": 5},
    }

    save_checkpoint(path, state)

    assert load_checkpoint(path) == state


def test_checkpoint_file_is_valid_json(tmp_path):
    path = tmp_path / "checkpoint.json"

    save_checkpoint(path, {"completed_rounds": 0})

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    assert payload["version"] == 1
    assert payload["state"]["completed_rounds"] == 0


def test_missing_checkpoint_raises_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_checkpoint(tmp_path / "missing.json")


def test_invalid_checkpoint_version_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(
        json.dumps({"version": 999, "state": {"completed_rounds": 1}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="version"):
        load_checkpoint(path)


def test_invalid_completed_rounds_is_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, {"completed_rounds": -1})

    with pytest.raises(ValueError, match="completed_rounds"):
        load_checkpoint(path)


def test_checkpoint_requires_completed_rounds(tmp_path):
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, {"red_state": {}})

    with pytest.raises(ValueError, match="completed_rounds"):
        load_checkpoint(path)