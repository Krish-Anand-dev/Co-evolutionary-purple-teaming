"""Compare measurement runs on the SAME first N prompts, from their raw answer files.

Usage: python scripts/compare_runs.py N label1=results/a.raw.jsonl label2=results/b.raw.jsonl ...
Prompt i uses the same agent id, round and feedback in every run (see measure_blue_validity.py), so with the same
seed the runs are paired. A prompt = one first call plus the repair call(s) right after it.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.agents.blue.repair import extract_rule_objects, normalise_rule  # noqa: E402
from src.rules.validator import validate_rule_dict  # noqa: E402


def summarise(path: str, limit: int) -> dict:
    rows = [json.loads(line) for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    groups: list[list[dict]] = []
    for r in rows:
        if r["is_repair"] and groups:
            groups[-1].append(r)
        else:
            groups.append([r])
    groups = groups[:limit]
    calls = [r for g in groups for r in g]
    objects = raw_ok = final_ok = no_valid = strict_fail = 0
    for g in groups:
        valid_in_group = 0
        for r in g:
            try:
                json.loads(r["text"])
            except json.JSONDecodeError:
                strict_fail += 1
            for i, obj in enumerate(extract_rule_objects(r["text"])):
                s = {**{k: v for k, v in obj.items() if k not in {"rule_id", "round", "agent_id"}},
                     "rule_id": f"x{i}", "round": 1, "agent_id": "blue_0"}
                objects += 1
                raw_ok += validate_rule_dict(s).valid
                ok = validate_rule_dict(normalise_rule(s)).valid
                final_ok += ok
                valid_in_group += ok
        no_valid += valid_in_group == 0
    n = len(calls)
    return {
        "prompts": len(groups), "calls": n, "repair_calls": n - len(groups), "rules": objects,
        "valid_as_written": raw_ok, "valid_after_fixes": final_ok,
        "validity_final": round(final_ok / objects, 3) if objects else 0.0,
        "prompts_with_no_valid_rule": no_valid, "not_strict_json": strict_fail,
        "hit_token_limit": sum(r["meta"].get("finish_reason") == "length" for r in calls),
        "mean_s_per_call": round(sum(r["meta"].get("latency_s") or 0 for r in calls) / n, 1) if n else 0.0,
        "mean_tokens_out": round(sum(r["meta"].get("tokens_out") or 0 for r in calls) / n) if n else 0,
    }


def main() -> None:
    limit = int(sys.argv[1])
    results = {}
    for spec in sys.argv[2:]:
        label, path = spec.split("=", 1)
        results[label] = summarise(path, limit)
    keys = list(next(iter(results.values())))
    width = max(len(k) for k in keys)
    print(f"{'':{width}}  " + "  ".join(f"{label:>14}" for label in results))
    for k in keys:
        print(f"{k:{width}}  " + "  ".join(f"{results[label][k]:>14}" for label in results))


if __name__ == "__main__":
    main()
