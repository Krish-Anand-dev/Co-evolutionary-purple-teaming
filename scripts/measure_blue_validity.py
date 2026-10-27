"""T18 acceptance: valid-rule rate over 50 prompts, written to results/.

Usage:
  python scripts/measure_blue_validity.py                       # mock LLM (pipeline test only)
  python scripts/measure_blue_validity.py --ollama qwen2.5:7b   # real model, on the GPU PC

The mock run measures our parsing/validation pipeline against an injected fault model. It says nothing
about how well a real LLM writes rules; only the --ollama run does.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.agents.blue import BlueLLMAgent, LlamaServerClient, MockLLMClient, OllamaClient  # noqa: E402


class RecordingClient:
    """Wraps any LLM client and appends every raw answer to a JSONL file for fault analysis."""

    def __init__(self, inner, path: pathlib.Path):
        self.inner, self.path, self.n = inner, path, 0

    def generate(self, prompt, schema=None):
        text, meta = self.inner.generate(prompt, schema)
        self.n += 1
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"call": self.n, "is_repair": "PREVIOUS ANSWER HAD" in prompt,
                                "text": text, "meta": meta}) + "\n")
        return text, meta


FEEDBACK_POOL = [
    "host server_2 needed Restore after repeated alerts",
    "reward penalty: green service access failed on subnet restricted_zone_a",
    "alerts on user_host_3 were followed by no further activity",
    "a decoy service was touched on server_1",
    "rule fired on 40 hosts in one step",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ollama", help="Ollama model name; omit for the mock LLM")
    ap.add_argument("--llama-server", help="llama-server base URL, e.g. http://127.0.0.1:8080")
    ap.add_argument("--label", default="llama-server", help="model name to record in the results")
    ap.add_argument("--n", type=int, default=50, help="number of prompts")
    ap.add_argument("--schema", action="store_true", help="constrain output with the basic JSON schema (llama-server only)")
    ap.add_argument("--schema-strict", action="store_true", help="schema that also restricts selection keys to the visible event fields")
    ap.add_argument("--schema-nested", action="store_true",
                    help="schema with selections BEFORE condition at rule level (combine with --schema-strict)")
    ap.add_argument("--max-tokens", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="results/t18_validity.json")
    args = ap.parse_args()
    logging.basicConfig(level=logging.ERROR)

    if args.llama_server:
        client = LlamaServerClient(args.llama_server, model=args.label, seed=args.seed, max_tokens=args.max_tokens)
    elif args.ollama:
        client = OllamaClient(args.ollama, seed=args.seed)
    else:
        client = MockLLMClient(seed=args.seed)
    raw_path = pathlib.Path(args.out).with_suffix(".raw.jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("")
    client = RecordingClient(client, raw_path)
    n_prompts = args.n
    totals = {"objects": 0, "valid_raw": 0, "valid_final": 0, "calls": 0, "fallbacks": 0, "duplicates": 0}
    latencies, per_prompt = [], []
    for i in range(n_prompts):
        # Fresh agent per prompt so prompts are independent samples (no accumulated rule memory).
        agent = BlueLLMAgent(f"blue_{i % 5}", client, use_schema=args.schema, strict_schema=args.schema_strict,
                             nested_schema=args.schema_nested)
        ctx = {"round": 1 + i % 10, "feedback": FEEDBACK_POOL[: 1 + i % len(FEEDBACK_POOL)], "last_alerts": []}
        agent.propose_rules(ctx)
        s = agent.history[-1]
        totals["objects"] += s.objects_found
        totals["valid_raw"] += s.valid_raw
        totals["valid_final"] += s.valid_final
        totals["calls"] += s.llm_calls
        totals["fallbacks"] += int(s.fallback)
        totals["duplicates"] += s.duplicates
        latencies.append(s.latency_s)
        per_prompt.append({"i": i, "objects": s.objects_found, "valid_raw": s.valid_raw,
                           "valid_final": s.valid_final, "calls": s.llm_calls, "fallback": s.fallback})

    result = {
        "llm": args.label if args.llama_server else args.ollama or "MOCK fault model (NOT a language model)",
        "seed": args.seed, "schema_constrained": ("nested" if args.schema_nested else "flat") + ("+strict" if args.schema_strict else "") if (args.schema or args.schema_strict or args.schema_nested) else False, "max_tokens": args.max_tokens, "n_prompts": n_prompts, **totals,
        "rule_validity_raw": totals["valid_raw"] / totals["objects"] if totals["objects"] else 0.0,
        "rule_validity_final": totals["valid_final"] / totals["objects"] if totals["objects"] else 0.0,
        "prompts_with_fallback": totals["fallbacks"],
        "mean_calls_per_prompt": totals["calls"] / n_prompts,
        "median_latency_s": statistics.median(latencies),
        "per_prompt": per_prompt,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "per_prompt"}, indent=1))


if __name__ == "__main__":
    main()
