# Scripted Red strategies (T19) - Krish

Code: `src/agents/red/scripted.py`. Run: `scripts/run_red_variants.py`. Tests: `tests/test_red_scripted.py`.
Raw results: `results/summaries/red_variants_tuning_seeds0-4.json`.

## What they are
CAGE-4's built-in Red (`FiniteStateRedAgent`) keeps a state per host (K known, S scanned, U user shell, R root; D = decoy
seen) and picks its next action from a probability table per state. Each variant below only overrides that table and the
host priority, so every action is a real CAGE-4 Red action and is legal by construction (Decision D3).
CybORG applies one Red class to all its Red agents, so one variant = one strategy for the whole attacker team.

| Name | Role | Behaviour |
|---|---|---|
| `cage4_default` | baseline Red | CAGE-4's own FSM, unchanged |
| `aggressive` | training | only the noisy scan (75% flagged), straight to exploit, root, then Impact / Degrade |
| `stealthy` | training | only the quiet scan (25% flagged), mostly discovery, strikes rarely |
| `deception_aware` | training | runs DiscoverDeception before exploiting; FSM then avoids services it saw to be decoys |
| `hit_and_run` | **HELD OUT** (T44) | mixes both scans, hits servers, Withdraws from hosts so Remove / Restore find nothing |

Rule: `hit_and_run` must not be used to train or tune Blue. It exists only for the generalisation test (T44).
`scripts/run_red_variants.py` accepts tuning seeds 0-9 only.

## Measured behaviour (passive Blue, 500-step episodes, tuning seeds 0-4, mean over seeds)
Red actions per episode, all Red agents summed ("Sleep" includes ticks spent waiting for a running action):

| Variant | AggrScan | StealthScan | DiscRemote | DiscDecep | Exploit | PrivEsc | Impact | Degrade | Withdraw |
|---|---|---|---|---|---|---|---|---|---|
| cage4_default | 42.8 | 41.8 | 39.2 | 86.0 | 234.2 | 52.8 | 337.6 | 357.6 | 0 |
| aggressive | 87.2 | 0 | 19.4 | 0 | 302.4 | 60.0 | 449.6 | 248.0 | 0 |
| stealthy | 0 | 87.4 | 53.0 | 30.8 | 280.8 | 60.4 | 309.2 | 311.6 | 0 |
| deception_aware | 16.8 | 70.4 | 39.0 | 148.0 | 244.6 | 55.6 | 296.8 | 292.4 | 0 |
| hit_and_run | 53.6 | 55.0 | 27.0 | 58.8 | 472.8 | 73.2 | 135.4 | 25.6 | 73.4 |

Other columns (mean over 5 seeds):

| Variant | Blue-visible native process records | Exploit success rate | First successful exploit (step) |
|---|---|---|---|
| cage4_default | 788 (sd 25) | 0.24 | 14.0 |
| aggressive | 928 (sd 48) | 0.21 | 16.6 |
| stealthy | 836 (sd 68) | 0.24 | 17.0 |
| deception_aware | 761 (sd 23) | 0.24 | 16.4 |
| hit_and_run | 916 (sd 119) | 0.29 | 15.8 |

## How to read this honestly
- The strategies clearly differ in WHAT they do (which scan, how often they probe for decoys, Impact vs Withdraw). That is
  the acceptance test (">= 3 distinct strategies, behavioural differences logged"), and it is met.
- They differ much less in how much native noise Blue sees. `aggressive` is the loudest (928 vs 788 for the default), but
  `stealthy` (836) is NOT quieter than the default: it explores more, so it triggers other records. Do not describe it as
  "quiet" in the paper without a closer look; "uses the low-detection scan" is accurate.
- 5 seeds, Blue passive. Against an acting Blue the picture will change. The Blue reward penalty was not logged here.
- "Records" counts native process records in Blue's observations, not alerts raised by any rule.

## A bug found and fixed on the way
The first version of `hit_and_run` could choose Withdraw on the single host where Red starts. That removes its only session,
so the agent slept for the rest of the episode (seeds 1-4 showed 1-3 actions). Withdraw is now offered only while the agent
holds shells on 2+ hosts; `tests/test_red_scripted.py` has a regression test on a stranding seed. The built-in agent avoids
the same trap by giving Withdraw probability 0 on those rows.
