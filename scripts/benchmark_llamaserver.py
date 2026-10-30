"""T09: time the REAL Blue rule-writing call against a running llama.cpp `llama-server` and write one CSV row per call.

Companion to scripts/benchmark_ollama.py (Prateek, T08), which targets Ollama and a generic SOC prompt. This one targets
the stack we actually use (llama-server, see docs/blue-agent-and-rules.md) and the prompt the Blue agent actually sends
(nested schema + limits hint), so the seconds-per-call it reports is the number the compute sheet needs (cell B4 of
'Experiments & Compute') and the truncation / validity columns show whether the model fits the token budget.

Start the server for ONE model, then run, for example:
  python scripts/benchmark_llamaserver.py --label gemma4-26b-a4b-q3 --runs 10 --out results/bench_llamaserver.csv
Run it once per model with a different --label and the same --out: rows are appended, so one CSV holds all models.
Stdlib plus the project's own Blue modules; no extra packages.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.agents.blue.llm_client import LlamaServerClient  # noqa: E402
from src.agents.blue.prompt import build_prompt  # noqa: E402
from src.agents.blue.repair import extract_rule_objects, normalise_rule  # noqa: E402
from src.agents.blue.schema import rule_json_schema  # noqa: E402
from src.rules.validator import validate_rule_dict  # noqa: E402

FIELDS = ["timestamp_utc", "model", "run", "latency_s", "prompt_tokens", "output_tokens", "output_tokens_per_s",
          "finish_reason", "truncated", "valid_json", "rules_found", "rules_valid", "error"]

# Same fictional round contexts the T18 validity runs use, so timings and validity are comparable with them.
FEEDBACK_POOL = [
    "host server_2 needed Restore after repeated alerts",
    "reward penalty: green service access failed on subnet restricted_zone_a",
    "alerts on user_host_3 were followed by no further activity",
    "a decoy service was touched on server_1",
    "rule fired on 40 hosts in one step",
]


def check_server(base_url: str, timeout: float) -> None:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=timeout) as resp:
            resp.read()
    except (OSError, urllib.error.URLError) as exc:
        raise SystemExit(f"Could not reach llama-server at {base_url}. Start it first. Details: {exc}")


def one_call(client: LlamaServerClient, schema: dict, index: int, max_rules: int, hint: bool = True) -> dict:
    ctx = {"round": 1 + index % 10, "agent_id": f"blue_{index % 5}",
           "feedback": FEEDBACK_POOL[: 1 + index % len(FEEDBACK_POOL)], "last_alerts": [], "previous_rules": []}
    prompt = build_prompt(ctx, max_rules, None, nested=True, hint=hint)
    text, meta = client.generate(prompt, schema)
    try:
        json.loads(text)
        valid_json = True
    except (json.JSONDecodeError, TypeError):
        valid_json = False
    objects = extract_rule_objects(text)[:max_rules]
    valid = 0
    for i, obj in enumerate(objects):
        stamped = {k: v for k, v in obj.items() if k not in {"rule_id", "round", "agent_id"}}
        stamped.update(rule_id=f"bench_{index}_{i}", round=ctx["round"], agent_id=ctx["agent_id"])
        valid += int(validate_rule_dict(normalise_rule(stamped)).valid)
    return {"meta": meta, "valid_json": valid_json, "rules_found": len(objects), "rules_valid": valid}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--label", required=True, help="model name to record in the CSV, e.g. qwen2.5-7b-q4_k_m")
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=1000, help="output cap; the Blue agent uses 1000")
    ap.add_argument("--max-rules", type=int, default=5)
    ap.add_argument("--no-hint", action="store_true", help="leave out the 'limits of the rule language' paragraph")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--out", default="results/bench_llamaserver.csv")
    args = ap.parse_args()
    if args.runs < 1 or args.warmup < 0 or args.max_tokens < 1:
        ap.error("--runs and --max-tokens must be positive; --warmup cannot be negative")

    check_server(args.url, 10)
    client = LlamaServerClient(args.url, model=args.label, seed=args.seed, max_tokens=args.max_tokens,
                               timeout_s=args.timeout)
    schema = rule_json_schema(args.max_rules, strict_fields=False, nested=True)

    for w in range(args.warmup):
        print(f"  warm-up {w + 1}/{args.warmup} ...", flush=True)
        one_call(client, schema, 1000 + w, args.max_rules, not args.no_hint)

    rows = []
    for run in range(1, args.runs + 1):
        client.seed = args.seed + run
        row = {k: "" for k in FIELDS}
        row.update(timestamp_utc=datetime.now(timezone.utc).isoformat(), model=args.label, run=run, valid_json=False)
        try:
            res = one_call(client, schema, run, args.max_rules, not args.no_hint)
            m = res["meta"]
            row.update(latency_s=round(m["latency_s"], 3), prompt_tokens=m.get("tokens_in") or "",
                       output_tokens=m.get("tokens_out") or "",
                       output_tokens_per_s=round(m["predicted_per_second"], 2) if m.get("predicted_per_second") else "",
                       finish_reason=m.get("finish_reason") or "", truncated=m.get("finish_reason") == "length",
                       valid_json=res["valid_json"], rules_found=res["rules_found"], rules_valid=res["rules_valid"])
            print(f"  run {run}/{args.runs}: {row['latency_s']} s, {row['output_tokens']} tok out, "
                  f"{row['rules_valid']}/{row['rules_found']} valid rules, finish={row['finish_reason']}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one failed call must not lose the others
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"  run {run}/{args.runs}: ERROR {row['error']}", flush=True)
        rows.append(row)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    new_file = not out.exists() or out.stat().st_size == 0
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r["latency_s"] != ""]
    print("\n" + "=" * 60)
    print(f"{args.label}: {len(ok)}/{len(rows)} calls succeeded")
    if ok:
        lat = [float(r["latency_s"]) for r in ok]
        print(f"  sec/call  median {statistics.median(lat):.1f}  mean {statistics.mean(lat):.1f}"
              + (f"  sd {statistics.stdev(lat):.1f}" if len(lat) > 1 else ""))
        tps = [float(r["output_tokens_per_s"]) for r in ok if r["output_tokens_per_s"] != ""]
        if tps:
            print(f"  tokens/s  median {statistics.median(tps):.1f}")
        print(f"  truncated at the token cap: {sum(r['truncated'] is True for r in ok)}/{len(ok)}")
        print(f"  answers that parse as JSON: {sum(r['valid_json'] is True for r in ok)}/{len(ok)}")
        found = sum(int(r["rules_found"]) for r in ok)
        valid = sum(int(r["rules_valid"]) for r in ok)
        print(f"  valid rules: {valid}/{found}" + (f" ({100 * valid / found:.1f}%)" if found else ""))
        print(f"  -> 'Experiments & Compute' B4 (seconds per LLM call) = {statistics.median(lat):.1f}")
    print(f"CSV appended to {out.resolve()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
