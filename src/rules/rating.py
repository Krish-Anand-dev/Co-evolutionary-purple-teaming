"""Human rating of rule quality (T31): blinded rating sheet + inter-rater agreement.

Blinding: the sheet shows only the rule content. rule_id, agent_id, round and condition are withheld
(they would reveal which system wrote the rule); items are shuffled with a seeded RNG across conditions.
The key that maps item_id -> condition is written to a SEPARATE file that raters must not open.
"""
from __future__ import annotations

import csv
import json
import random
from itertools import combinations
from pathlib import Path
from typing import Any

DIMENSIONS = ("clarity", "actionability", "plausibility", "fp_risk")
SCALE = (1, 2, 3, 4, 5)
SHEET_FIELDS = ["item_id", "title", "level", "logsource_category", "selections", "condition",
                "confidence", "rationale"]


def _selections_text(detection: dict[str, Any]) -> str:
    return "; ".join(f"{name}: {json.dumps(sel, sort_keys=True)}"
                     for name, sel in detection.items() if name != "condition")


def build_rating_items(conditions: dict[str, list[dict[str, Any]]], n_per_condition: int,
                       seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (sheet_rows, key_rows). Same inputs + seed -> identical output."""
    rng = random.Random(seed)
    picked: list[tuple[str, dict[str, Any]]] = []
    for cond in sorted(conditions):                      # sorted: independent of dict order
        rules = list(conditions[cond])
        rng.shuffle(rules)
        picked += [(cond, r) for r in rules[:n_per_condition]]
    rng.shuffle(picked)                                  # mix conditions together
    sheet, key = [], []
    for i, (cond, r) in enumerate(picked, start=1):
        item_id = f"item_{i:03d}"
        sheet.append({
            "item_id": item_id, "title": r["title"], "level": r["level"],
            "logsource_category": r["logsource"]["category"],
            "selections": _selections_text(r["detection"]), "condition": r["detection"]["condition"],
            "confidence": r["confidence"], "rationale": r.get("rationale", ""),
        })
        key.append({"item_id": item_id, "condition": cond, "rule_id": r.get("rule_id", "")})
    return sheet, key


def write_rating_files(sheet: list[dict[str, Any]], key: list[dict[str, Any]], out_dir: str | Path,
                       raters: list[str]) -> None:
    """One blank rating CSV per rater (same items, same order) plus the private key."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for rater in raters:
        with (out / f"ratings_{rater}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SHEET_FIELDS + list(DIMENSIONS))
            writer.writeheader()
            writer.writerows({**row, **{d: "" for d in DIMENSIONS}} for row in sheet)
    with (out / "KEY_do_not_open_until_all_rated.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["item_id", "condition", "rule_id"])
        writer.writeheader()
        writer.writerows(key)


def quadratic_weighted_kappa(a: list[int], b: list[int], categories: tuple[int, ...] = SCALE) -> float:
    """Cohen's kappa with quadratic weights for two raters on an ordinal scale (1.0 = perfect, 0 = chance).
    Returns nan if the expected disagreement is zero (e.g. both raters always give the same single score)."""
    if len(a) != len(b) or not a:
        raise ValueError("rating lists must be the same non-zero length")
    k, n = len(categories), len(a)
    idx = {c: i for i, c in enumerate(categories)}
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    row = [sum(r) for r in obs]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * obs[i][j]
            den += w * row[i] * col[j] / n
    return float("nan") if den == 0 else 1.0 - num / den


def read_ratings(path: str | Path) -> dict[str, dict[str, int]]:
    """item_id -> {dimension: score}. Raises if any score is missing or outside 1..5."""
    out: dict[str, dict[str, int]] = {}
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            scores = {}
            for d in DIMENSIONS:
                try:
                    v = int(row[d])
                except (TypeError, ValueError):
                    raise ValueError(f"{path}: {row['item_id']} has no score for '{d}'") from None
                if v not in SCALE:
                    raise ValueError(f"{path}: {row['item_id']} '{d}' = {v} outside 1..5")
                scores[d] = v
            out[row["item_id"]] = scores
    return out


def pairwise_agreement(by_rater: dict[str, dict[str, dict[str, int]]]) -> dict[str, dict[str, float]]:
    """{dimension: {'raterA|raterB': kappa, ..., 'mean': average of the finite pairwise values}}."""
    result: dict[str, dict[str, float]] = {}
    for d in DIMENSIONS:
        pairs: dict[str, float] = {}
        for r1, r2 in combinations(sorted(by_rater), 2):
            common = sorted(set(by_rater[r1]) & set(by_rater[r2]))
            pairs[f"{r1}|{r2}"] = quadratic_weighted_kappa(
                [by_rater[r1][i][d] for i in common], [by_rater[r2][i][d] for i in common])
        finite = [v for v in pairs.values() if v == v]
        pairs["mean"] = sum(finite) / len(finite) if finite else float("nan")
        result[d] = pairs
    return result
