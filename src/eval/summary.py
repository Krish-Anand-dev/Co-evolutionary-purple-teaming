"""Experiment tables from the JSONL logs (T25): per-seed values -> mean with a bootstrap 95% CI per condition and round.

Reads the contract's round records (see src/loop/logger.py ROUND_FIELDS). A metric that is null in a record is skipped and
counted as missing, never treated as 0. Each seed contributes ONE number per group (the mean of its non-null values), and the
bootstrap resamples seeds, so the interval reflects seed-to-seed variation, which is what 10 seeds can tell us.
Pure Python (no numpy / pandas) so it runs in every environment of the project.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.eval.stats import DEFAULT_RESAMPLES, bootstrap_ci, mean, paired_diff_ci

DEFAULT_METRICS = ("precision", "recall", "fpr", "time_to_detect", "rule_validity", "red_success")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n}: not valid JSON ({exc})") from exc
    return out


def split_records(records: Iterable[Mapping[str, Any]]) -> tuple[list[Mapping], list[Mapping]]:
    """(step records, round records). A step record has a `step`; a round record has `rules_emitted` and no `step`."""
    steps, rounds = [], []
    for r in records:
        if "step" in r:
            steps.append(r)
        elif "rules_emitted" in r:
            rounds.append(r)
    return steps, rounds


def per_seed_values(records: Iterable[Mapping[str, Any]], metric: str,
                    group_by: Sequence[str] = ("condition", "round")) -> dict[tuple, dict[Any, float]]:
    """{group key: {seed: value}} with one value per seed (mean of that seed's non-null values). Seeds whose values are all
    null appear with None so callers can count them as missing."""
    raw: dict[tuple, dict[Any, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        key = tuple(r[g] for g in group_by)
        bucket = raw[key][r["seed"]]
        if r.get(metric) is not None:
            bucket.append(float(r[metric]))
    return {k: {seed: (mean(v) if v else None) for seed, v in seeds.items()} for k, seeds in raw.items()}


def summarise(records: Iterable[Mapping[str, Any]], metrics: Sequence[str] = DEFAULT_METRICS,
              group_by: Sequence[str] = ("condition", "round"), n_resamples: int = DEFAULT_RESAMPLES,
              confidence: float = 0.95, seed: int = 0) -> list[dict[str, Any]]:
    """Long-format table: one row per (group, metric) with n_seeds, n_missing, mean, ci_low, ci_high.
    A metric that is null for every record of the whole log is omitted rather than reported as empty rows."""
    records = list(records)
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        if not any(r.get(metric) is not None for r in records):
            continue
        for key, by_seed in sorted(per_seed_values(records, metric, group_by).items(), key=lambda kv: tuple(map(str, kv[0]))):
            vals = [v for v in by_seed.values() if v is not None]
            est, lo, hi = bootstrap_ci(vals, n_resamples, confidence, seed)
            row = dict(zip(group_by, key))
            row.update(metric=metric, n_seeds=len(vals), n_missing=len(by_seed) - len(vals), mean=est, ci_low=lo, ci_high=hi)
            rows.append(row)
    return rows


def compare_conditions(records: Iterable[Mapping[str, Any]], metric: str, cond_a: str, cond_b: str,
                       round_number: int | None = None, n_resamples: int = DEFAULT_RESAMPLES, seed: int = 0) -> dict[str, Any]:
    """Paired (by seed) difference cond_a - cond_b for one metric: mean, bootstrap CI and exact sign-flip p-value.
    round_number=None averages each seed over all rounds first."""
    records = [r for r in records if r["condition"] in (cond_a, cond_b)
               and (round_number is None or r["round"] == round_number)]
    by = per_seed_values(records, metric, group_by=("condition",))
    out = paired_diff_ci(by.get((cond_a,), {}), by.get((cond_b,), {}), n_resamples=n_resamples, seed=seed)
    out.update(metric=metric, a=cond_a, b=cond_b, round=round_number)
    return out


def _fmt(x: float | None, digits: int) -> str:
    return "-" if x is None else f"{x:.{digits}f}"


def format_table(rows: Sequence[Mapping[str, Any]], metric: str, digits: int = 3) -> str:
    """Markdown table for ONE metric: a row per group with `mean [ci_low, ci_high] (n seeds)`. This is also the table view
    the figures need, since some palette colours fall below 3:1 contrast."""
    sel = [r for r in rows if r["metric"] == metric]
    if not sel:
        return f"(no data for {metric})"
    keys = [k for k in sel[0] if k not in ("metric", "n_seeds", "n_missing", "mean", "ci_low", "ci_high")]
    head = "| " + " | ".join(keys + [metric + " mean [95% CI]", "n seeds", "missing"]) + " |"
    sep = "|" + "---|" * (len(keys) + 3)
    body = []
    for r in sel:
        ci = "" if r["ci_low"] is None else f" [{_fmt(r['ci_low'], digits)}, {_fmt(r['ci_high'], digits)}]"
        body.append("| " + " | ".join([str(r[k]) for k in keys] + [_fmt(r["mean"], digits) + ci, str(r["n_seeds"]),
                                                                        str(r["n_missing"])]) + " |")
    return "\n".join([head, sep, *body])


def write_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    if not rows:
        raise ValueError("no rows to write")
    fields = list(rows[0])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
