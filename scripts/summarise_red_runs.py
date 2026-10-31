"""Summarise one or more T28 experiment logs (JSONL from scripts/run_red_experiment.py) into a table per condition.

  python scripts/summarise_red_runs.py --inputs results/t28_cage4_default.jsonl results/t28_aggressive.jsonl \
      --compare static_rules_vs_aggressive static_rules_vs_cage4_default \
      --out results/summaries/t28_summary.json --md results/summaries/t28_summary.md

Per condition: mean over seeds with a 95% bootstrap CI over seeds (src/eval). --compare A B (repeatable) adds the paired-by-seed
difference A - B with its CI and the exact sign-flip p-value, for every metric in --metrics. With several comparisons the
p-values are exploratory: do not read them as confirmatory tests.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.summary import compare_conditions, format_table, read_jsonl, split_records, summarise  # noqa: E402

DEFAULT_METRICS = ("precision", "recall", "fpr", "time_to_detect", "red_success", "detection_rate")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--metrics", nargs="+", default=list(DEFAULT_METRICS))
    ap.add_argument("--compare", nargs=2, action="append", metavar=("A", "B"), default=[])
    ap.add_argument("--group-by", nargs="+", default=["condition"], help="e.g. condition round")
    ap.add_argument("--resamples", type=int, default=10_000)
    ap.add_argument("--out", default=None)
    ap.add_argument("--md", default=None)
    ap.add_argument("--title", default="Summary of T28 runs")
    args = ap.parse_args()

    rounds = []
    for path in args.inputs:
        rounds += split_records(read_jsonl(path))[1]
    if not rounds:
        raise SystemExit("no round records found")
    rows = summarise(rounds, metrics=args.metrics, group_by=args.group_by, n_resamples=args.resamples)
    comps = [compare_conditions(rounds, m, a, b, n_resamples=args.resamples)
             for a, b in args.compare for m in args.metrics if any(r.get(m) is not None for r in rounds)]

    md = [f"# {args.title}", "", f"Inputs: {', '.join(args.inputs)}. Mean over seeds, 95% bootstrap CI over seeds.", ""]
    for m in args.metrics:
        if any(r["metric"] == m for r in rows):
            md += [f"### {m}", "", format_table(rows, m), ""]
    if comps:
        md += ["### Paired comparisons (A - B, same seeds; exploratory)", "",
               "| A | B | metric | n seeds | mean difference [95% CI] | sign-flip p |", "|---|---|---|---|---|---|"]
        for c in comps:
            if c["n"] and c["ci_low"] is not None:
                md.append(f"| {c['a']} | {c['b']} | {c['metric']} | {c['n']} | {c['mean_diff']:+.3f} [{c['ci_low']:+.3f}, {c['ci_high']:+.3f}]"
                          f" | {c['p_sign_flip']:.3f} |")
        md.append("")
    text = "\n".join(md)
    print(text)
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"inputs": args.inputs, "summary": rows, "comparisons": comps,
                                   "per_seed": [{k: v for k, v in r.items() if k not in ("red_plan",)} for r in rounds]},
                                  indent=2, allow_nan=False, default=str) + "\n", encoding="utf-8")
        print("wrote", out)
    if args.md:
        pathlib.Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.md).write_text(text + "\n", encoding="utf-8")
        print("wrote", args.md)


if __name__ == "__main__":
    main()
