"""Run real CAGE-4 episodes with the real Red agents through the T22 experiment runner (T28).

Needs CAGE-4 cloned to external/cage-challenge-4 and the pinned environment (docs/setup.md). Examples:
  # static rule set as the detector against CAGE-4's default Red, tuning seeds, 500 steps
  python scripts/run_red_experiment.py --config configs/red_static_baseline.yaml --output results/t28_static.jsonl
  # the LLM Red (needs a running llama-server, see docs/red-llm-agent.md), 3 seeds, 5 rounds
  python scripts/run_red_experiment.py --config configs/red_static_baseline.yaml --red llm --llama-server http://127.0.0.1:8080 \
      --seeds 0 1 2 --rounds 5 --output results/t28_llm.jsonl
  # no GPU: the fault-injecting mock LLM
  python scripts/run_red_experiment.py --config configs/red_static_baseline.yaml --red llm --mock-llm --rounds 3 --seeds 0

The YAML is the normal T22 experiment config; an optional `real_episode:` block (red, blue, rules, memory_dir) sets the defaults
that the flags override. Seeds come from the config's seed list for the chosen --seed-set (tuning 0-9 by default). The held-out
Red strategy (hit_and_run) is refused on tuning seeds. Episodes run one at a time (one process-wide labeler).
Blue is a passive / decoy stand-in and does not act on the rules: this measures Red and the rules-as-detector until T27.
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAGE4 = ROOT / "external" / "cage-challenge-4"
if not CAGE4.exists():
    raise SystemExit("CAGE-4 not found: clone it to external/cage-challenge-4 (see docs/setup.md)")
sys.path.insert(0, str(CAGE4))
sys.path.insert(0, str(ROOT))

from src.agents.blue.llm_client import LlamaServerClient  # noqa: E402
from src.agents.red.mock_llm import MockRedLLM  # noqa: E402
from src.agents.red.scripted import ALL  # noqa: E402
from src.eval.summary import format_table, read_jsonl, split_records, summarise  # noqa: E402
from src.loop.config import load_config  # noqa: E402
from src.loop.real_episode import LLM_RED, RealEpisodeRunner, RealEpisodeSettings, round_extras  # noqa: E402
from src.loop.runner import run_experiment  # noqa: E402

METRICS = ("precision", "recall", "fpr", "time_to_detect", "red_success")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/red_static_baseline.yaml")
    ap.add_argument("--output", default="results/t28_experiment.jsonl")
    ap.add_argument("--condition", default=None, help="condition name to log (default: the one in the config)")
    ap.add_argument("--seed-set", choices=("tuning", "test"), default="tuning")
    ap.add_argument("--seeds", type=int, nargs="+", default=None, help="subset of the configured seeds to run")
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--episodes-per-round", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--red", default=None, help=f"'llm' or one of {sorted(ALL)}")
    ap.add_argument("--blue", choices=("passive", "decoy"), default=None)
    ap.add_argument("--rules", default=None, help="JSON rule set used as the detector ('none' = no rules)")
    ap.add_argument("--memory-dir", default=None, help="where the per-seed Red memory files go (red=llm)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--llama-server", metavar="URL", help="llama-server base URL for red=llm")
    g.add_argument("--mock-llm", action="store_true", help="use the fault-injecting mock LLM for red=llm (no GPU)")
    ap.add_argument("--model", default="local", help="model name to record for the LLM")
    ap.add_argument("--temperature", type=float, default=0.7)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = load_config(args.config)
    raw = yaml.safe_load(pathlib.Path(args.config).read_text(encoding="utf-8")).get("real_episode", {}) or {}
    rules = args.rules if args.rules is not None else raw.get("rules")
    settings = RealEpisodeSettings(
        red=args.red or raw.get("red", "cage4_default"), blue=args.blue or raw.get("blue", "passive"),
        rules_path=None if rules in (None, "none") else str(ROOT / rules) if not pathlib.Path(rules).is_absolute() else rules,
        memory_dir=args.memory_dir or raw.get("memory_dir"))

    overrides = {k: v for k, v in (("rounds", args.rounds), ("episodes_per_round", args.episodes_per_round), ("steps", args.steps)) if v}
    if args.seeds:
        field_name = "tuning_seeds" if args.seed_set == "tuning" else "test_seeds"
        allowed = set(getattr(config, field_name))
        bad = [s for s in args.seeds if s not in allowed]
        if bad:
            raise SystemExit(f"seeds {bad} are not in the configured {args.seed_set} seeds {sorted(allowed)}")
        overrides[field_name] = tuple(args.seeds)
    if args.condition:
        overrides["condition"] = args.condition
    config = dataclasses.replace(config, **overrides)

    client = None
    if settings.red == LLM_RED:
        if args.mock_llm:
            client = MockRedLLM(seed=config.seed)
        elif args.llama_server:
            client = LlamaServerClient(args.llama_server, model=args.model, temperature=args.temperature, seed=config.seed, max_tokens=400)
        else:
            raise SystemExit("red=llm needs --llama-server URL or --mock-llm")

    runner = RealEpisodeRunner(settings, llm_client=client)
    try:
        summary = run_experiment(config, args.output, max_workers=1, seed_set=args.seed_set, episode_fn=runner,
                                 round_extras_fn=round_extras)
    finally:
        runner.close()
    print("\nrun summary:", summary)

    _, rounds = split_records(read_jsonl(args.output))
    rows = summarise(rounds, metrics=METRICS, group_by=("condition", "round"), n_resamples=2000)
    for m in METRICS:
        if any(r["metric"] == m for r in rows):
            print(f"\n### {m}\n\n{format_table(rows, m)}")
    print(f"\nlogs: {args.output}  (red={settings.red} blue={settings.blue} rules={settings.rules_path or 'none'})")


if __name__ == "__main__":
    main()
