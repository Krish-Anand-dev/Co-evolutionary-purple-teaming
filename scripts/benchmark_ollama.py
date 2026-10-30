
#!/usr/bin/env python3
"""Benchmark Ollama models on a realistic SOC detection-engineering prompt."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROMPT = """
You are assisting a security operations centre (SOC) detection engineer.
Analyse the following fictional but realistic security telemetry scenario
and propose one detection rule. Return exactly one JSON object, without
Markdown fences or explanatory text.

ENVIRONMENT:
The organisation operates Windows 10 and Windows 11 endpoints, Windows
Server domain controllers, Microsoft 365, VPN gateways, and an internal
EDR platform. Authentication events are forwarded to a central SIEM.
Endpoint clocks are synchronised to the organisation's time source.
The SIEM stores event timestamps in UTC and retains 90 days of searchable
telemetry. Hostnames and user identifiers are pseudonymised in this example.

SCENARIO:
During a 20-minute period, several accounts generated repeated failed
authentication events against multiple Windows endpoints. A subset of
these accounts subsequently generated successful logons from the same
source address. Some source addresses belong to approved vulnerability
scanners, while others are not present in the approved scanner inventory.
The activity is not sufficient by itself to establish malicious intent.
The detection should identify suspicious patterns while avoiding an
unnecessarily broad alert.

RELEVANT TELEMETRY:
- Windows Security Event ID 4625: failed logon.
- Windows Security Event ID 4624: successful logon.
- Event fields may include timestamp, computer, target username,
  source network address, logon type, and status code.
- Network addresses may be missing or represented as "-".
- Service accounts and approved scanners can produce repeated failures.
- A successful logon after repeated failures is useful context, but should
  not be treated as proof of compromise.
- Events may arrive late or out of order.
- Duplicate events may exist in the SIEM.

TASK:
Create a practical candidate detection rule for this scenario. Define a
reasonable correlation window and threshold, explain the logic, identify
important exclusions, and describe how an analyst should validate an alert.
Do not invent organisation-specific facts or claim that the scenario proves
an account was compromised.

Return this JSON structure:
{
  "rule_name": "short descriptive name",
  "description": "one or two concise sentences",
  "severity": "low, medium, or high",
  "log_source": ["relevant telemetry sources"],
  "detection_logic": {
    "events": ["event identifiers"],
    "threshold": "proposed threshold",
    "correlation_window": "proposed time window",
    "conditions": ["clear detection conditions"]
  },
  "false_positive_notes": ["likely benign explanations"],
  "recommended_exclusions": ["carefully scoped exclusions"],
  "analyst_validation": ["steps an analyst should take"],
  "limitations": ["important limitations"]
}

Keep the response concise but sufficiently specific for an engineer
to review. Use valid JSON and do not add keys outside this structure.
"""


def request_ollama(
    host: str,
    model: str,
    prompt: str,
    *,
    timeout: float,
    seed: int,
    temperature: float,
    num_predict: int,
) -> dict[str, Any]:
    """Send one non-streaming generation request to Ollama."""
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "seed": seed,
            "num_predict": num_predict,
        },
    }

    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed = time.perf_counter() - started

    return {
        "response": payload.get("response", ""),
        "latency_s": elapsed,
        "prompt_tokens": payload.get("prompt_eval_count"),
        "output_tokens": payload.get("eval_count"),
        "total_duration_ns": payload.get("total_duration"),
        "load_duration_ns": payload.get("load_duration"),
        "generation_duration_ns": payload.get("eval_duration"),
    }


def check_ollama(host: str, timeout: float) -> None:
    """Fail early if the Ollama server cannot be reached."""
    request = urllib.request.Request(f"{host.rstrip('/')}/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Could not reach Ollama at {host}. Is Ollama running? Details: {exc}"
        ) from exc


def is_valid_json(response: str) -> bool:
    try:
        json.loads(response)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def benchmark_model(args: argparse.Namespace, model: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    print(f"\nModel: {model}")

    for warmup_index in range(args.warmup):
        print(f"  Warm-up {warmup_index + 1}/{args.warmup}...")
        request_ollama(
            args.host,
            model,
            PROMPT,
            timeout=args.timeout,
            seed=args.seed,
            temperature=args.temperature,
            num_predict=args.num_predict,
        )

    for run_index in range(1, args.runs + 1):
        print(f"  Run {run_index}/{args.runs}...", end=" ", flush=True)
        started_at = datetime.now(timezone.utc).isoformat()

        row: dict[str, Any] = {
            "timestamp_utc": started_at,
            "model": model,
            "run": run_index,
            "latency_s": "",
            "prompt_tokens": "",
            "output_tokens": "",
            "output_tokens_per_s": "",
            "valid_json": False,
            "error": "",
        }

        try:
            result = request_ollama(
                args.host,
                model,
                PROMPT,
                timeout=args.timeout,
                seed=args.seed + run_index,
                temperature=args.temperature,
                num_predict=args.num_predict,
            )

            output_tokens = result["output_tokens"]
            generation_ns = result["generation_duration_ns"]
            tokens_per_second = ""

            if output_tokens and generation_ns and generation_ns > 0:
                tokens_per_second = output_tokens / (generation_ns / 1_000_000_000)

            row.update(
                {
                    "latency_s": round(result["latency_s"], 4),
                    "prompt_tokens": result["prompt_tokens"] or "",
                    "output_tokens": output_tokens or "",
                    "output_tokens_per_s": (
                        round(tokens_per_second, 3)
                        if tokens_per_second != ""
                        else ""
                    ),
                    "valid_json": is_valid_json(result["response"]),
                }
            )
            print(
                f"{result['latency_s']:.2f}s | "
                f"JSON: {'valid' if row['valid_json'] else 'INVALID'}"
            )

        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            print(f"ERROR: {row['error']}")

        rows.append(row)

    return rows


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 65)
    print("BENCHMARK SUMMARY")
    print("=" * 65)

    models = sorted({row["model"] for row in rows})

    for model in models:
        model_rows = [row for row in rows if row["model"] == model]
        successful = [row for row in model_rows if row["latency_s"] != ""]
        latencies = [float(row["latency_s"]) for row in successful]
        valid_count = sum(row["valid_json"] is True for row in successful)

        if not successful:
            print(f"\n{model}: no successful measured calls")
            continue

        mean_latency = statistics.mean(latencies)
        median_latency = statistics.median(latencies)
        valid_rate = 100 * valid_count / len(successful)

        print(f"\n{model}")
        print(f"  Successful calls: {len(successful)}/{len(model_rows)}")
        print(f"  Mean latency:     {mean_latency:.2f} sec/call")
        print(f"  Median latency:   {median_latency:.2f} sec/call")
        print(f"  Valid JSON rate:  {valid_rate:.1f}%")

        if len(latencies) > 1:
            print(f"  Latency SD:       {statistics.stdev(latencies):.2f} sec")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark local Ollama models on a SOC detection prompt."
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated Ollama model tags, e.g. qwen2.5:3b,qwen2.5:7b",
    )
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--num-predict", type=int, default=250)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument(
        "--out",
        default="results/ollama_benchmark.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    if args.runs < 1 or args.warmup < 0 or args.num_predict < 1:
        parser.error("--runs and --num-predict must be positive; --warmup cannot be negative")

    models = [item.strip() for item in args.models.split(",") if item.strip()]
    if not models:
        parser.error("Provide at least one model using --models")

    try:
        check_ollama(args.host, args.timeout)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    all_rows: list[dict[str, Any]] = []

    for model in models:
        all_rows.extend(benchmark_model(args, model))

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp_utc",
        "model",
        "run",
        "latency_s",
        "prompt_tokens",
        "output_tokens",
        "output_tokens_per_s",
        "valid_json",
        "error",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print_summary(all_rows)
    print(f"\nCSV saved to: {output_path.resolve()}")

    return 0 if any(row["latency_s"] != "" for row in all_rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
