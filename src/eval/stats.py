"""Small, dependency-free statistics for the experiment tables (T25): bootstrap CIs across seeds and paired comparisons.

Why pure Python: the Blue-side test environment has no numpy, and 10 seeds x 10,000 resamples is cheap.
Unit of resampling is the SEED: every metric is first reduced to one number per seed (see summary.py) and the
bootstrap resamples those numbers with replacement. With only 10 seeds a percentile bootstrap is crude (the interval is
often a little narrow); report n next to every interval, which summary.py does.
"""
from __future__ import annotations

import itertools
import math
import random
from typing import Callable, Mapping, Sequence

DEFAULT_RESAMPLES = 10_000


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean of an empty sequence")
    return math.fsum(values) / len(values)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile of an ascending list (same convention as numpy's default)."""
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    pos = q * (len(sorted_values) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_ci(values: Sequence[float], n_resamples: int = DEFAULT_RESAMPLES, confidence: float = 0.95,
                 seed: int = 0, stat: Callable[[Sequence[float]], float] = mean
                 ) -> tuple[float | None, float | None, float | None]:
    """(estimate, low, high): the statistic on the data and its percentile-bootstrap interval.

    Deterministic for a given `seed`. Needs >= 2 values for an interval; with 1 value the estimate is returned and the
    interval is (None, None); with 0 values everything is None.
    """
    vals = [float(v) for v in values]
    if not vals:
        return None, None, None
    estimate = stat(vals)
    if len(vals) < 2:
        return estimate, None, None
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    rng = random.Random(seed)
    n = len(vals)
    stats = sorted(stat([vals[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples))
    alpha = 1.0 - confidence
    return estimate, _quantile(stats, alpha / 2), _quantile(stats, 1 - alpha / 2)


def paired_differences(a: Mapping, b: Mapping) -> dict:
    """{key: a[key] - b[key]} over keys (e.g. seeds) present in both with a value in each (None is skipped)."""
    return {k: a[k] - b[k] for k in a if k in b and a[k] is not None and b[k] is not None}


def paired_diff_ci(a: Mapping, b: Mapping, n_resamples: int = DEFAULT_RESAMPLES, confidence: float = 0.95,
                   seed: int = 0) -> dict:
    """Mean paired difference a - b over shared seeds with its bootstrap CI and the exact sign-flip p-value.

    Pairing by seed is the point: both conditions saw the same simulator seeds, so the per-seed difference removes the
    seed-to-seed variation. Returns {"n", "mean_diff", "ci_low", "ci_high", "p_sign_flip"}.
    """
    diffs = list(paired_differences(a, b).values())
    est, lo, hi = bootstrap_ci(diffs, n_resamples, confidence, seed)
    return {"n": len(diffs), "mean_diff": est, "ci_low": lo, "ci_high": hi,
            "p_sign_flip": sign_flip_pvalue(diffs) if diffs else None}


def sign_flip_pvalue(diffs: Sequence[float], max_exact: int = 16, n_mc: int = 100_000, seed: int = 0) -> float:
    """Two-sided paired sign-flip (randomisation) test of 'the mean difference is 0'.

    Under the null each paired difference is equally likely to have either sign. The p-value is the share of sign
    patterns whose |sum| is at least the observed |sum|. Exact enumeration for <= `max_exact` non-zero differences,
    otherwise Monte Carlo (seeded). Zero differences carry no information and are dropped.
    """
    d = [float(x) for x in diffs if x != 0]
    if not d:
        return 1.0
    observed = abs(math.fsum(d))
    tol = 1e-12 * max(1.0, observed)
    if len(d) <= max_exact:
        hits = sum(abs(math.fsum(s * x for s, x in zip(signs, d))) >= observed - tol
                   for signs in itertools.product((1, -1), repeat=len(d)))
        return hits / 2 ** len(d)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_mc):
        if abs(math.fsum(x if rng.random() < 0.5 else -x for x in d)) >= observed - tol:
            hits += 1
    return (hits + 1) / (n_mc + 1)
