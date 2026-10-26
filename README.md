# Co-Evolutionary Purple Teaming for Automated SOC Detection Engineering

An LLM Red agent and an LLM Blue agent play self-play rounds (one side frozen while the
other updates) inside CybORG / CAGE Challenge 4. Blue emits human-readable Sigma-style
detection rules. Runs on local LLMs (Ollama) on a single consumer GPU.

Authors: Bhavit Anand, Krish Anand, Prateek Tanwar (MAIT, GGSIPU, Delhi).

## Layout

| Path | Contents | Owner |
|---|---|---|
| `src/agents/` | `blue/`, `red/`, `baselines/`; mock agents (`random_blue`, `random_red`) | Krish |
| `src/rules/` | Rule dataclass, validator, executor, response playbook | Bhavit |
| `src/bridge/` | Telemetry bridge (CAGE-4 state -> synthetic events) and ground-truth labeler | Bhavit / Krish |
| `src/loop/` | Co-evolution loop, reward functions, checkpoints | Prateek |
| `src/eval/` | Metrics, bootstrap CIs, plots | Krish |
| `configs/` | YAML experiment configs | |
| `docs/` | Setup notes, cheat sheet, tuning log | |
| `scripts/` | Helper scripts | |
| `tests/` | pytest | |
| `results/` | Raw logs are gitignored; commit summaries under `results/summaries/` | |

The shapes of rules, events, agent APIs, logs and configs are defined in the
Interface Contract tab of the execution plan (frozen in T03).

## Conventions

- Python with type hints; `ruff` + `black`; `pytest` for every module; `logging`, not `print()`.
- Times in seconds. Seeds: tuning 0-9, test 100-109; never tune on test seeds.
- Branches: `feat/T##-short-name`. Every PR needs one review from another author.
- Every module must run against mock agents / mock events.

## Setup

See `docs/setup.md` (written in T04).
