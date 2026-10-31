"""T25 metrics + stats + tables + plots, verified on a hand-computed toy example (numbers worked out on paper, see comments)."""
from __future__ import annotations

import json
import math

import pytest

from src.eval import (bootstrap_ci, compare_conditions, episodes_from_step_records, evaluate_episode,
                      format_table, paired_diff_ci, read_jsonl, red_success, round_metrics, sign_flip_pvalue,
                      split_records, summarise, write_csv)
from src.eval.stats import _quantile
from src.loop.logger import ExperimentLogger

# ---------------------------------------------------------------- hand-computed toy data
# Episode A: id, step, label_red, alerted
#   a1 1 0 no (TN)   a2 3 1 no (FN)   a3 4 1 YES (TP)   a4 5 0 YES (FP)
#   a5 6 1 YES (TP)  a6 7 0 no (TN)   a7 8 0 no (TN)    a8 9 1 no (FN)
#   TP=2 FP=1 FN=2 TN=3 -> precision 2/3, recall 2/4, fpr 1/4; first red 3, first detect 4 -> time to detect 1
A = [("a1", 1, 0), ("a2", 3, 1), ("a3", 4, 1), ("a4", 5, 0), ("a5", 6, 1), ("a6", 7, 0), ("a7", 8, 0), ("a8", 9, 1)]
A_ALERTED = ["a3", "a4", "a5"]
# Episode B: b1 2 red no (FN), b2 5 red no (FN), b3 6 benign no (TN), b4 7 benign YES (FP)
#   TP=0 FP=1 FN=2 TN=1 -> precision 0/1=0, recall 0/2=0, fpr 1/2; first red 2, never detected; last step 9 -> censored 9-2=7
B = [("b1", 2, 1), ("b2", 5, 1), ("b3", 6, 0), ("b4", 7, 0)]
B_ALERTED = ["b4"]
# Episode C: two benign events, no alerts: TP=0 FP=0 FN=0 TN=2 -> precision None, recall None, fpr 0/2=0; no red events
C = [("c1", 1, 0), ("c2", 2, 0)]


def ev(rows):
    return [{"event_id": i, "step": s, "label_red": lab} for i, s, lab in rows]


def episode(rows, alerted, last):
    return evaluate_episode(ev(rows), alerted, last_step=last)


# ---------------------------------------------------------------- episode metrics
def test_episode_a_matches_hand_calculation():
    m = episode(A, A_ALERTED, 10)
    assert (m.tp, m.fp, m.fn, m.tn) == (2, 1, 2, 3)
    assert m.precision == pytest.approx(2 / 3) and m.recall == 0.5 and m.fpr == 0.25
    assert (m.first_red_step, m.first_detect_step, m.time_to_detect) == (3, 4, 1)


def test_duplicate_alerts_on_one_event_count_once():
    twice = A_ALERTED + ["a3", "a3"]
    assert episode(A, twice, 10) == episode(A, A_ALERTED, 10)


def test_alert_objects_and_dicts_are_accepted():
    from types import SimpleNamespace
    objs = [SimpleNamespace(event_id=i) for i in A_ALERTED]
    dicts = [{"event_id": i, "rule_id": "r"} for i in A_ALERTED]
    assert episode(A, objs, 10) == episode(A, dicts, 10) == episode(A, A_ALERTED, 10)


def test_episode_b_never_detected_is_none_and_censored():
    m = episode(B, B_ALERTED, 9)
    assert (m.tp, m.fp, m.fn, m.tn) == (0, 1, 2, 1)
    assert m.precision == 0.0 and m.recall == 0.0 and m.fpr == 0.5   # 0 is a real value here, not "undefined"
    assert m.time_to_detect is None and not m.detected
    assert m.time_to_detect_censored == 7


def test_episode_c_without_red_events_has_undefined_ratios():
    m = episode(C, [], 5)
    assert (m.tp, m.fp, m.fn, m.tn) == (0, 0, 0, 2)
    assert m.precision is None and m.recall is None and m.fpr == 0.0
    assert m.time_to_detect is None and m.time_to_detect_censored is None


def test_pipeline_bugs_raise_instead_of_hiding_in_a_metric():
    with pytest.raises(ValueError, match="no ground-truth label"):
        evaluate_episode([{"event_id": "x", "step": 1, "label_red": None}], [])
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_episode(ev([("x", 1, 0), ("x", 2, 1)]), [])
    with pytest.raises(ValueError, match="unknown event"):
        evaluate_episode(ev([("x", 1, 0)]), ["nope"])


# ---------------------------------------------------------------- round metrics (pooled A + B + C)
def test_round_pooling_matches_hand_calculation():
    r = round_metrics([episode(A, A_ALERTED, 10), episode(B, B_ALERTED, 9), episode(C, [], 5)])
    # pooled: TP 2, FP 2, FN 4, TN 6
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (2, 2, 4, 6)
    assert r["precision"] == 0.5 and r["recall"] == pytest.approx(1 / 3) and r["fpr"] == 0.25
    assert r["episodes"] == 3 and r["episodes_with_red_events"] == 2
    assert r["detection_rate"] == 0.5            # A detected, B not, C has no red events
    assert r["time_to_detect"] == 1.0            # mean over detected episodes only
    assert r["time_to_detect_censored"] == 4.0   # (1 + 7) / 2


def test_round_with_nothing_detected_reports_none_not_zero():
    r = round_metrics([episode(B, [], 9)])
    assert r["time_to_detect"] is None and r["detection_rate"] == 0.0 and r["precision"] is None


# ---------------------------------------------------------------- red success helper
def test_red_success_counts_only_successful_impacts():
    log = [{"action": "Impact", "success": "TRUE"}, {"action": "Impact", "success": "TernaryEnum.TRUE"},
           {"action": "Impact", "success": "FALSE"}, {"action": "ExploitRemoteService", "success": "TRUE"},
           {"action": "Impact", "success": True}]
    assert red_success(log) == 3 and red_success(log, "ExploitRemoteService") == 1


# ---------------------------------------------------------------- step-log path
STEPS = [  # step, tp, fp, fn, tn
    (1, 0, 0, 0, 5), (2, 0, 0, 1, 4), (3, 1, 0, 0, 4), (4, 0, 2, 0, 3), (5, 2, 0, 1, 2), (6, 0, 0, 0, 5)]


def step_records(with_tn):
    out = []
    for step, tp, fp, fn, tn in STEPS:
        r = {"run_id": "r", "condition": "c", "seed": 0, "round": 1, "episode": 1, "step": step, "tp": tp, "fp": fp, "fn": fn}
        if with_tn:
            r["tn"] = tn
        out.append(r)
    return out


def test_step_records_give_hand_calculated_round_metrics():
    # totals tp 3, fp 2, fn 2; red present from step 2, first detected at step 3 -> time to detect 1
    (m,) = episodes_from_step_records(step_records(with_tn=False)).values()
    assert (m.tp, m.fp, m.fn) == (3, 2, 2) and m.tn is None
    assert m.precision == 0.6 and m.recall == 0.6 and m.fpr is None
    assert m.time_to_detect == 1 and m.last_step == 6
    (m2,) = episodes_from_step_records(step_records(with_tn=True)).values()
    assert m2.tn == 23 and m2.fpr == pytest.approx(2 / 25)


# ---------------------------------------------------------------- statistics
def test_quantile_interpolates_like_numpy():
    xs = [1, 2, 3, 4]
    assert (_quantile(xs, 0), _quantile(xs, 1), _quantile(xs, 0.5), _quantile(xs, 0.25)) == (1, 4, 2.5, 1.75)


def test_bootstrap_ci_known_cases():
    # two values 0 and 1: resampled means are 0, .5, 1 with probabilities 1/4, 1/2, 1/4 -> 95% interval is exactly [0, 1]
    assert bootstrap_ci([0, 1], n_resamples=20_000, seed=1) == (0.5, 0.0, 1.0)
    assert bootstrap_ci([3, 3, 3], n_resamples=500) == (3.0, 3.0, 3.0)
    assert bootstrap_ci([7]) == (7.0, None, None)
    assert bootstrap_ci([]) == (None, None, None)


def test_bootstrap_is_deterministic_per_seed_and_covers_the_mean():
    vals = [0.2, 0.4, 0.5, 0.6, 0.9, 0.7, 0.3, 0.5, 0.6, 0.4]
    a = bootstrap_ci(vals, seed=5)
    assert a == bootstrap_ci(vals, seed=5)
    est, lo, hi = a
    assert est == pytest.approx(0.51) and lo < est < hi and 0.2 <= lo and hi <= 0.9


def test_sign_flip_exact_values():
    assert sign_flip_pvalue([1, 2, 3]) == 0.25           # only the all-plus and all-minus patterns reach |sum| = 6: 2/8
    assert sign_flip_pvalue([1, 1, 1, 1]) == 0.125       # 2/16
    assert sign_flip_pvalue([2, -1]) == 1.0              # every pattern has |sum| >= 1
    assert sign_flip_pvalue([0, 0]) == 1.0 and sign_flip_pvalue([]) == 1.0
    assert 0 < sign_flip_pvalue([1.0] * 20) < 0.001      # Monte Carlo branch, strongly one-sided


def test_paired_diff_ci_pairs_by_seed_and_skips_missing():
    a = {0: 0.9, 1: 0.8, 2: 0.7, 3: 0.5}
    b = {0: 0.5, 1: 0.6, 2: 0.4, 3: None}      # seed 3 has no value for b: dropped, not treated as 0
    out = paired_diff_ci(a, b, n_resamples=2000)
    assert out["n"] == 3 and out["mean_diff"] == pytest.approx(0.3)
    assert out["p_sign_flip"] == 0.25 and out["ci_low"] <= 0.3 <= out["ci_high"]
    assert out["ci_low"] >= 0.2 - 1e-9 and out["ci_high"] <= 0.4 + 1e-9   # diffs are .4, .2, .3 (float rounding)


# ---------------------------------------------------------------- tables from round records
def rr(condition, rnd, seed, **metrics):
    base = {"run_id": "r", "condition": condition, "seed": seed, "round": rnd, "rules_emitted": 5, "rules_valid": 5,
            "rule_validity": 1.0, "precision": None, "recall": None, "fpr": None, "red_success": None, "time_to_detect": None}
    base.update(metrics)
    return base


RECORDS = (
    [rr("static", 1, s, precision=p) for s, p in zip(range(4), (0.2, 0.4, 0.6, None))]     # mean 0.4, one seed missing
    + [rr("coevo", 1, s, precision=p) for s, p in zip(range(4), (0.5, 0.6, 0.7, 0.8))]     # mean 0.65
    + [rr("coevo", 2, s, precision=p) for s, p in zip(range(4), (0.7, 0.8, 0.9, 1.0))]     # mean 0.85
)


def test_summarise_means_counts_and_missing():
    rows = summarise(RECORDS, metrics=("precision",), n_resamples=2000)
    by = {(r["condition"], r["round"]): r for r in rows}
    s1, c1, c2 = by[("static", 1)], by[("coevo", 1)], by[("coevo", 2)]
    assert s1["mean"] == pytest.approx(0.4) and s1["n_seeds"] == 3 and s1["n_missing"] == 1
    assert c1["mean"] == pytest.approx(0.65) and c2["mean"] == pytest.approx(0.85) and c1["n_missing"] == 0
    assert s1["ci_low"] <= 0.4 <= s1["ci_high"] and 0.2 <= s1["ci_low"] and s1["ci_high"] <= 0.6


def test_summarise_omits_metrics_that_are_null_everywhere():
    rows = summarise(RECORDS, metrics=("precision", "fpr"))
    assert {r["metric"] for r in rows} == {"precision"}


def test_compare_conditions_is_paired_by_seed():
    # round 1, seeds 0-2 have both: coevo - static = .5-.2, .6-.4, .7-.6 = .3, .2, .1 -> mean .2; seed 3 is missing in static
    out = compare_conditions(RECORDS, "precision", "coevo", "static", round_number=1, n_resamples=2000)
    assert out["n"] == 3 and out["mean_diff"] == pytest.approx(0.2) and out["p_sign_flip"] == 0.25


def test_format_table_and_csv(tmp_path):
    rows = summarise(RECORDS, metrics=("precision",), n_resamples=500)
    table = format_table(rows, "precision")
    assert "| condition | round | precision mean [95% CI] | n seeds | missing |" in table
    assert "| static | 1 | 0.400 [" in table and "| 3 | 1 |" in table
    assert format_table(rows, "recall") == "(no data for recall)"
    write_csv(rows, tmp_path / "t.csv")
    assert (tmp_path / "t.csv").read_text(encoding="utf-8").splitlines()[0].startswith("condition,round,metric")


# ---------------------------------------------------------------- compatibility with the T22 logger (null metrics, no NaN)
def test_reads_what_the_t22_logger_writes(tmp_path):
    path = tmp_path / "log.jsonl"
    with ExperimentLogger(path) as log:
        for s in range(2):
            log.log_round({"run_id": "r", "condition": "c", "seed": s, "round": 1, "rules_emitted": 3, "rules_valid": 2,
                           "rule_validity": 2 / 3, "precision": 0.5 + s / 10, "recall": None, "fpr": None,
                           "red_success": None, "time_to_detect": None})
        for rec in step_records(with_tn=False):
            log.log_step({**rec, "phase": "eval", "agent": "a", "action": None, "reward_components": {}, "alerts": [],
                          "active_rules": [], "llm_calls": 0, "llm_latency_s": 0.0})
    steps, rounds = split_records(read_jsonl(path))
    assert len(steps) == 6 and len(rounds) == 2
    rows = summarise(rounds, metrics=("precision", "recall", "rule_validity"), n_resamples=200)
    assert {r["metric"] for r in rows} == {"precision", "rule_validity"}   # recall is null everywhere -> omitted
    (m,) = episodes_from_step_records(steps).values()
    assert m.precision == 0.6
    with pytest.raises(ValueError, match="not valid JSON"):
        (tmp_path / "bad.jsonl").write_text("{oops\n", encoding="utf-8")
        read_jsonl(tmp_path / "bad.jsonl")


# ---------------------------------------------------------------- plots
def test_plots_are_written_and_validated(tmp_path):
    pytest.importorskip("matplotlib")
    from src.eval.plots import MAX_CONDITIONS, plot_condition_bars, plot_round_curves

    rows = summarise(RECORDS, metrics=("precision",), n_resamples=500)
    png = plot_round_curves(rows, "precision", tmp_path / "curve.png", conditions=["static", "coevo"], title="toy")
    bars = plot_condition_bars(rows, "precision", tmp_path / "bars.png", conditions=["static", "coevo"], round_number=1)
    for p in (png, bars):
        data = p.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 5_000
    with pytest.raises(ValueError, match="no rows for metric"):
        plot_round_curves(rows, "recall", tmp_path / "x.png")
    with pytest.raises(ValueError, match="no rows for condition"):
        plot_round_curves(rows, "precision", tmp_path / "x.png", conditions=["static", "ghost"])
    many = [{**r, "condition": f"c{i}"} for i in range(MAX_CONDITIONS + 1) for r in rows[:1]]
    with pytest.raises(ValueError, match="at most"):
        plot_round_curves(many, "precision", tmp_path / "x.png")


def test_no_nan_leaks_into_summaries():
    rows = summarise(RECORDS, metrics=("precision",), n_resamples=200)
    for r in rows:
        for k in ("mean", "ci_low", "ci_high"):
            assert r[k] is None or not math.isnan(r[k])
    json.dumps(rows, allow_nan=False)  # same rule the JSONL logger enforces
