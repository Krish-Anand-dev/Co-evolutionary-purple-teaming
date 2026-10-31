# Static baseline re-check against the real bridge (T23a / T16) - Bhavit, 31-Oct-2026

Why: the 10 hand-written rules (`configs/static_blue_rules.json`) were written in week 1 against the DRAFT event vocabulary,
with a note to re-check them once the bridge existed. Krish's T25 end-to-end run (docs/metrics-and-stats.md) gave FPR 0.69.

## What was wrong
Three rules (static_03, 05, 10) used `parent_process|endswith: "d"` to mean "a service daemon". The bridge gives benign Green
alerts the parent `systemd`, which also ends in "d", so every benign process event matched. Per-rule counts, passive Blue,
FSM Red, seeds 0-2, 500 steps (369 benign / 1,964 red events):

| rule | benign alerts before | red alerts before | benign after | red after |
|---|---|---|---|---|
| static_03 | 166 | 30 | 0 | 132 |
| static_05 | 41 | 30 | 0 | 132 |
| static_08 (restricted zone, level low) | 99 | 759 | 99 | 759 |

## Change
`parent_process` is now matched against the explicit daemon list `sshd, apache2, haraka, tomcat` (the parents the bridge
uses for exploit sessions). Nothing else changed.

## Result (tuning seeds 0-9, passive and decoy Blue, `scripts/eval_static_baseline.py`)
| metric | before | after |
|---|---|---|
| precision | 0.86 | 0.95 |
| recall | 0.90 | 0.95 |
| FPR | 0.69 | 0.25 |

The remaining FPR is mostly static_08, a deliberately broad low-level rule.

## Caveats (state these in the paper)
- The list is tied to the bridge's INVENTED parent names, so this baseline is tuned to our own enrichment. It is a stronger
  baseline, which makes the LLM-vs-static comparison harder for us, not easier.
- Tuning seeds only; test seeds 100-109 untouched.
- Time to detect is 0 for every run (rules fire on the first scan), so it says nothing yet.
- Checked Krish's finding 2 (T21): under a traffic-blocking Blue, 1,471 of 1,489 benign connection events are port 8800
  failures with sensible addresses; only 18 have an ephemeral destination port. No rule uses addresses, so no bridge change was made.
