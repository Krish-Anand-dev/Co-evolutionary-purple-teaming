"""Detection metrics for one episode / one round (T25): precision, recall, false-positive rate, time to detect.

Definitions (event level, using the ground-truth label from T21, src/bridge/labeler.py):
  an event is ALERTED when at least one active rule fired on it (several rules on one event still count once)
  TP = red events alerted        FN = red events not alerted
  FP = benign events alerted     TN = benign events not alerted
  precision = TP / (TP + FP)     recall = TP / (TP + FN)      fpr = FP / (FP + TN)
  Any ratio whose denominator is 0 is None (never 0 or 1), and the JSONL logger needs None because it rejects NaN.
Time to detect, per episode: (step of the first alerted red event) - (step of the first red event), in env steps, or None
if Red produced no events or none of them was alerted. A round with several episodes pools the counts (micro average) and
reports the mean time to detect over the episodes where Red was detected, the detection rate, and a censored variant in
which an undetected episode counts as (episode length - first red step).

Caveat to keep in the paper: counts are over EVENTS, and Red scans/exploits produce many events per action, so a rule that
catches the noisiest action can have high event recall while missing whole attack stages. time_to_detect is the campaign-level
complement. Event labels are only as complete as the bridge: red actions that leave no event (PrivilegeEscalate, Impact, ...
unless synthetic events are enabled) cannot be missed or caught here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


def ratio(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


@dataclass(frozen=True)
class EpisodeMetrics:
    n_events: int
    tp: int
    fp: int
    fn: int
    tn: int | None                 # None when only step logs without a true-negative count are available
    first_red_step: int | None
    first_detect_step: int | None
    last_step: int | None          # index of the episode's final step (same indexing as `step`); only used for censoring

    @property
    def precision(self) -> float | None:
        return ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return ratio(self.tp, self.tp + self.fn)

    @property
    def fpr(self) -> float | None:
        return None if self.tn is None else ratio(self.fp, self.fp + self.tn)

    @property
    def detected(self) -> bool:
        return self.first_red_step is not None and self.first_detect_step is not None

    @property
    def time_to_detect(self) -> int | None:
        return self.first_detect_step - self.first_red_step if self.detected else None

    @property
    def time_to_detect_censored(self) -> int | None:
        """Undetected episodes count as (last step - first red step); None when Red produced no events."""
        if self.first_red_step is None:
            return None
        if self.detected:
            return self.time_to_detect
        return None if self.last_step is None else max(self.last_step - self.first_red_step, 0)


def _get(obj: Any, name: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def evaluate_episode(events: Iterable[Any], alerts: Iterable[Any], last_step: int | None = None) -> EpisodeMetrics:
    """Confusion counts and detection timing for one episode.

    events: objects or dicts with event_id, step, label_red (0/1), e.g. bridge Events or their to_log() dicts.
    alerts: rule Alerts, dicts with event_id, or bare event ids.
    last_step: index of the episode's final step (e.g. 498 for a 499-step CAGE-4 episode), for the censored time to detect.
    Raises ValueError for an unlabelled event, a duplicate event id, or an alert on an unknown event: these are bugs in the
    pipeline and must not be absorbed into a metric.
    """
    by_id: dict[Any, tuple[int, int]] = {}
    for e in events:
        eid, step, label = _get(e, "event_id"), _get(e, "step"), _get(e, "label_red")
        if label not in (0, 1):
            raise ValueError(f"event {eid!r} has no ground-truth label (label_red={label!r})")
        if eid in by_id:
            raise ValueError(f"duplicate event_id {eid!r}")
        by_id[eid] = (int(step), int(label))
    alerted: set[Any] = set()
    for a in alerts:
        eid = a if not isinstance(a, (Mapping,)) and not hasattr(a, "event_id") else _get(a, "event_id")
        if eid not in by_id:
            raise ValueError(f"alert on unknown event {eid!r}")
        alerted.add(eid)

    tp = fp = fn = tn = 0
    first_red: int | None = None
    first_detect: int | None = None
    for eid, (step, label) in by_id.items():
        hit = eid in alerted
        if label == 1:
            first_red = step if first_red is None else min(first_red, step)
            if hit:
                tp += 1
                first_detect = step if first_detect is None else min(first_detect, step)
            else:
                fn += 1
        elif hit:
            fp += 1
        else:
            tn += 1
    return EpisodeMetrics(len(by_id), tp, fp, fn, tn, first_red, first_detect, last_step)


def round_metrics(episodes: Sequence[EpisodeMetrics]) -> dict[str, Any]:
    """Pool the episodes of one (seed, round). Keys match the contract's round record (precision, recall, fpr,
    time_to_detect) plus the counts and detection rate that explain them."""
    if not episodes:
        raise ValueError("no episodes")
    tp, fp, fn = (sum(getattr(e, k) for e in episodes) for k in ("tp", "fp", "fn"))
    tn = None if any(e.tn is None for e in episodes) else sum(e.tn for e in episodes)
    with_red = [e for e in episodes if e.first_red_step is not None]
    ttd = [e.time_to_detect for e in episodes if e.detected]
    ttd_c = [e.time_to_detect_censored for e in with_red if e.time_to_detect_censored is not None]
    return {
        "episodes": len(episodes), "episodes_with_red_events": len(with_red),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, tp + fn),
        "fpr": None if tn is None else ratio(fp, fp + tn),
        "detection_rate": ratio(len(ttd), len(with_red)),
        "time_to_detect": (sum(ttd) / len(ttd)) if ttd else None,
        "time_to_detect_censored": (sum(ttd_c) / len(ttd_c)) if len(ttd_c) == len(with_red) and ttd_c else None,
    }


_TRUE = {"TRUE", "TERNARYENUM.TRUE", "TRINARYENUM.TRUE"}


def red_success(action_log: Iterable[Mapping[str, Any]], action: str = "Impact") -> int:
    """Number of successful `action` (default Impact, Red's objective) in a Red action log (T21 `labeler.action_log`).
    This is a PROPOSAL for the contract's `red_success`; the team has not fixed its definition yet."""
    n = 0
    for r in action_log:
        s = r.get("success")
        ok = s is True or (isinstance(s, str) and s.upper() in _TRUE)
        n += r.get("action") == action and ok
    return n


def episodes_from_step_records(records: Iterable[Mapping[str, Any]]) -> dict[tuple, EpisodeMetrics]:
    """One EpisodeMetrics per (run_id, condition, seed, round, episode) from the contract's STEP records.

    Uses the per-step tp / fp / fn. Red was present on a step when tp + fn > 0 and detected when tp > 0. `tn` is not in the
    contract's step record: if records carry an optional `tn` it is summed and FPR works; otherwise FPR is None. (Proposed
    to Prateek: add `tn` to the step record.)
    """
    acc: dict[tuple, dict[str, Any]] = {}
    for r in records:
        key = (r.get("run_id"), r["condition"], r["seed"], r["round"], r["episode"])
        a = acc.setdefault(key, {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "has_tn": True, "first_red": None,
                                 "first_detect": None, "last": 0})
        tp, fp, fn = int(r["tp"]), int(r["fp"]), int(r["fn"])
        a["tp"] += tp
        a["fp"] += fp
        a["fn"] += fn
        if r.get("tn") is None:
            a["has_tn"] = False
        else:
            a["tn"] += int(r["tn"])
        step = int(r["step"])
        a["last"] = max(a["last"], step)
        if tp + fn > 0:
            a["first_red"] = step if a["first_red"] is None else min(a["first_red"], step)
        if tp > 0:
            a["first_detect"] = step if a["first_detect"] is None else min(a["first_detect"], step)
    return {k: EpisodeMetrics(n_events=v["tp"] + v["fp"] + v["fn"] + (v["tn"] if v["has_tn"] else 0), tp=v["tp"],
                              fp=v["fp"], fn=v["fn"], tn=v["tn"] if v["has_tn"] else None,
                              first_red_step=v["first_red"], first_detect_step=v["first_detect"],
                              last_step=v["last"]) for k, v in acc.items()}
