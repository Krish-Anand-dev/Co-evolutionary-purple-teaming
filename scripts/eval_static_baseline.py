"""T25 end-to-end check on REAL episodes: the static hand-written ruleset (configs/static_blue_rules.json) as a detector.

Needs CAGE-4 cloned to external/cage-challenge-4 and its environment active (docs/setup.md), and the T21 labeler
(src/bridge/labeler.py). Example:
  python scripts/eval_static_baseline.py --out results/summaries/static_baseline_metrics.json --md results/summaries/static_baseline_metrics.md

For each Blue behaviour (passive, decoy-deploying) and each tuning seed 0-9 it plays one full 500-step episode against CAGE-4's
FiniteStateRedAgent, feeds the bridge (with the ground-truth labeler) the raw Blue observations, runs the static rules on the
Blue-visible events, and computes precision / recall / FPR / time to detect with src/eval. The Blue here does NOT use the rules
to act: this measures the rules as detectors only. Numbers are a baseline for the pipeline, not a result of the paper.
Only tuning seeds 0-9 are accepted; test seeds 100-109 stay untouched.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import label_check as lc  # noqa: E402  (also puts CAGE-4 on sys.path)

from src.bridge import GroundTruthLabeler  # noqa: E402
from src.eval import evaluate_episode, format_table, red_success, round_metrics, summarise  # noqa: E402
from src.rules.executor import RuleExecutor  # noqa: E402
from src.rules.loader import load_rules  # noqa: E402

TUNING_SEEDS = range(0, 10)
METRICS = ("precision", "recall", "fpr", "time_to_detect", "red_success")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=list(TUNING_SEEDS))
    ap.add_argument("--blues", nargs="+", default=["passive", "decoy"], choices=["passive", "decoy"])
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--rules", default=str(ROOT / "configs" / "static_blue_rules.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--md", default=None)
    ap.add_argument("--png", default=None, help="bar chart of precision / recall by Blue behaviour")
    args = ap.parse_args()
    bad = [s for s in args.seeds if s not in TUNING_SEEDS]
    if bad:
        raise SystemExit(f"seeds {bad} are not tuning seeds (0-9)")

    rules = load_rules(args.rules)
    executor = RuleExecutor(rules)
    if executor.rejected:
        raise SystemExit(f"rules rejected by the validator: {executor.rejected}")

    records, details = [], []
    labeler = GroundTruthLabeler().install()
    try:
        for blue in args.blues:
            for seed in args.seeds:
                res, events, action_log = lc.run(blue, "fsm", seed, args.steps, labeler)
                if res["n_problems"] or res["unlabelled"]:
                    raise SystemExit(f"labelling problem on {blue} seed {seed}: {res['problems']}")
                alerts = executor.run(e.visible() for e in events)
                last = max((e.step for e in events), default=0)
                ep = evaluate_episode(events, alerts, last_step=res["steps"] - 1)
                rm = round_metrics([ep])
                records.append({
                    "run_id": "static_baseline", "condition": f"static_rules_{blue}_blue", "seed": seed, "round": 1,
                    "rules_emitted": len(rules), "rules_valid": len(executor.rules), "rule_validity": len(executor.rules) / len(rules),
                    "precision": rm["precision"], "recall": rm["recall"], "fpr": rm["fpr"],
                    "red_success": red_success(action_log), "time_to_detect": rm["time_to_detect"]})
                details.append({"blue": blue, "seed": seed, "events": ep.n_events, "tp": ep.tp, "fp": ep.fp, "fn": ep.fn,
                                "tn": ep.tn, "alerted_events": ep.tp + ep.fp, "first_red_step": ep.first_red_step,
                                "first_detect_step": ep.first_detect_step, "last_event_step": last})
                print(f"{blue:8s} seed {seed}: events {ep.n_events:4d} TP {ep.tp:4d} FP {ep.fp:3d} FN {ep.fn:4d} TN {ep.tn:4d} "
                      f"precision {ep.precision if ep.precision is None else round(ep.precision, 3)} "
                      f"recall {ep.recall if ep.recall is None else round(ep.recall, 3)} "
                      f"fpr {ep.fpr if ep.fpr is None else round(ep.fpr, 3)} ttd {ep.time_to_detect}")
    finally:
        labeler.uninstall()

    rows = summarise(records, metrics=METRICS, group_by=("condition", "round"))
    md = "\n\n".join(f"### {m}\n\n{format_table(rows, m)}" for m in METRICS if any(r["metric"] == m for r in rows))
    print("\n" + md)
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"rules": args.rules, "n_rules": len(rules), "seeds": args.seeds, "summary": rows,
                                   "per_seed": records, "episodes": details}, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print("wrote", out)
    if args.md:
        p = pathlib.Path(args.md)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Static ruleset as a detector (T25 end-to-end check)\n\n"
                     f"{len(rules)} hand-written rules, CAGE-4 FiniteStateRedAgent, tuning seeds {args.seeds}, 500 steps. "
                     "Mean over seeds with 95% bootstrap CI over seeds.\n\n" + md + "\n", encoding="utf-8")
        print("wrote", p)
    if args.png:
        from src.eval.plots import plot_condition_bars
        conds = sorted({r["condition"] for r in rows})
        for m in ("precision", "recall"):
            if any(r["metric"] == m for r in rows):
                print("wrote", plot_condition_bars(rows, m, pathlib.Path(args.png).with_name(f"{pathlib.Path(args.png).stem}_{m}.png"),
                                                    conditions=conds, round_number=1, title=f"Static rules: {m} (FSM Red)"))


if __name__ == "__main__":
    main()
